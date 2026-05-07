"""
Calendar API router — free-slot, meeting suggestion, and event creation endpoints.

Routes:
    GET  /calendar/free-slots   → return free time slots within a date range (Req 6.1)
    POST /calendar/suggest      → suggest up to 3 meeting times (rate-limited 30/min, Req 6.6, 6.7, 12.4)
    POST /calendar/events       → create a calendar event (Req 6.8)

Requirements: 6.1, 6.6, 6.7, 6.8, 12.4
"""

# from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import openai
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, get_db
from backend.models.db_models import Email as EmailORM
from backend.schemas.pydantic_schemas import (
    CalendarEvent,
    CalendarSuggestRequest,
    EmailMessage,
    MeetingSlot,
    TimeSlot,
    User,
)
from backend.services.calendar_service import CalendarService, DateRange
from backend.services.decision_engine import DecisionEngine
from backend.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Service factory helpers
# ---------------------------------------------------------------------------


def _make_calendar_service(session: AsyncSession) -> CalendarService:
    """
    Instantiate CalendarService with all required dependencies.

    Uses the OPENAI_API_KEY environment variable for the OpenAI client.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    openai_sync_client = openai.OpenAI(api_key=api_key)
    openai_async_client = openai.AsyncOpenAI(api_key=api_key)

    decision_engine = DecisionEngine(
        openai_client=openai_async_client,
        session=session,
    )

    return CalendarService(
        session=session,
        decision_engine=decision_engine,
        openai_client=openai_sync_client,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/free-slots",
    response_model=List[TimeSlot],
    summary="Return free time slots within a date range",
)
async def get_free_slots(
    start_date: str = Query(..., description="Start date in ISO format (e.g. 2024-01-15 or 2024-01-15T09:00:00)"),
    end_date: str = Query(..., description="End date in ISO format (e.g. 2024-01-22 or 2024-01-22T18:00:00)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TimeSlot]:
    """
    Return free time slots within the specified date range, filtered by the
    user's working hours and existing calendar events.

    Query parameters:
    - ``start_date``: ISO date or datetime string for the range start.
    - ``end_date``: ISO date or datetime string for the range end.

    Returns a list of TimeSlot objects sorted ascending by start time.
    Only slots within the user's configured working hours are returned.

    Requirements: 6.1
    """
    # Parse ISO date strings — accept both date-only and full datetime formats
    try:
        # Try full datetime first, then date-only
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            start_dt = datetime.fromisoformat(start_date + "T00:00:00")

        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            end_dt = datetime.fromisoformat(end_date + "T23:59:59")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: {exc}. Use ISO format (e.g. 2024-01-15 or 2024-01-15T09:00:00).",
        ) from exc

    # Ensure timezone-aware datetimes
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    if end_dt <= start_dt:
        raise HTTPException(
            status_code=422,
            detail="end_date must be after start_date.",
        )

    user_id = str(current_user.id)
    calendar_service = _make_calendar_service(db)
    date_range = DateRange(start=start_dt, end=end_dt)

    free_slots = await calendar_service.get_free_slots(user_id, date_range)

    logger.info(
        "GET /calendar/free-slots — user=%s, start=%s, end=%s, slots=%d",
        user_id,
        start_date,
        end_date,
        len(free_slots),
    )
    return free_slots


@router.post(
    "/suggest",
    response_model=List[MeetingSlot],
    summary="Suggest up to 3 meeting times (rate-limited: 30 req/min)",
)
@limiter.limit("30/minute")
async def suggest_meeting_times(
    request: Request,
    body: CalendarSuggestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[MeetingSlot]:
    """
    Suggest up to 3 AI-ranked meeting time slots based on the user's free
    calendar slots for the next 7 days.

    Request body:
    - ``email_id``: UUID of the meeting-request email to suggest times for.

    Fetches the email from the database, queries free slots for the next 7 days,
    and returns up to 3 ranked MeetingSlot suggestions.

    Rate-limited to 30 requests per minute per IP.

    Requirements: 6.6, 6.7, 12.4
    """
    user_id = str(current_user.id)
    user_uuid = current_user.id

    # Fetch the email from the database
    stmt = (
        select(EmailORM)
        .where(EmailORM.id == body.email_id, EmailORM.user_id == user_uuid)
    )
    result = await db.execute(stmt)
    email_row = result.scalar_one_or_none()

    if email_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Email {body.email_id} not found.",
        )

    email = EmailMessage.model_validate(email_row)

    calendar_service = _make_calendar_service(db)
    meeting_slots = await calendar_service.suggest_meeting_times(user_id, email)

    logger.info(
        "POST /calendar/suggest — user=%s, email_id=%s, suggestions=%d",
        user_id,
        body.email_id,
        len(meeting_slots),
    )
    return meeting_slots


class CreateCalendarEventRequest(BaseModel):
    """Request body for POST /calendar/events."""

    slot: MeetingSlot
    attendees: List[str]
    email_id: Optional[UUID] = None


@router.post(
    "/events",
    response_model=CalendarEvent,
    summary="Create a calendar event for a confirmed meeting slot",
)
async def create_calendar_event(
    body: CreateCalendarEventRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarEvent:
    """
    Create a Google Calendar event for the confirmed meeting slot.

    Request body:
    - ``slot``: MeetingSlot containing the time window and reason.
    - ``attendees``: List of attendee email addresses.
    - ``email_id``: Optional UUID of the email that triggered this meeting.

    Persists the event to the calendar_events table and records an analytics
    event. Returns the created CalendarEvent.

    Requirements: 6.8
    """
    user_id = str(current_user.id)
    calendar_service = _make_calendar_service(db)

    event = await calendar_service.create_event(
        user_id=user_id,
        slot=body.slot,
        attendees=body.attendees,
        email_id=str(body.email_id) if body.email_id else None,
    )

    logger.info(
        "POST /calendar/events — user=%s, event_id=%s, attendees=%d",
        user_id,
        event.id,
        len(body.attendees),
    )
    return event
