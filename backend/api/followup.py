"""
Follow-up API router — follow-up management endpoints.

Routes:
    GET  /followups                             → list pending follow-ups (Req 7.1–7.4)
    POST /followups/{followup_id}/snooze        → snooze a follow-up (Req 7.6)
    POST /followups/{followup_id}/resolve       → resolve a follow-up (Req 7.7)
    POST /followups/{followup_id}/generate-draft → generate a follow-up draft (Req 7.5)

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from uuid import UUID

import openai
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, get_db
from backend.schemas.pydantic_schemas import FollowupSuggestion, ReplyDraft, User
from backend.services.decision_engine import DecisionEngine
from backend.services.followup_agent import FollowupAgent

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SnoozeRequest(BaseModel):
    """Request body for POST /followups/{followup_id}/snooze."""

    until: datetime


# ---------------------------------------------------------------------------
# Service factory helper
# ---------------------------------------------------------------------------


def _make_followup_agent(session: AsyncSession) -> FollowupAgent:
    """Instantiate FollowupAgent with a DecisionEngine."""
    api_key = os.getenv("OPENAI_API_KEY")
    openai_async_client = openai.AsyncOpenAI(api_key=api_key)
    decision_engine = DecisionEngine(
        openai_client=openai_async_client,
        session=session,
    )
    return FollowupAgent(decision_engine=decision_engine)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[FollowupSuggestion],
    summary="List pending follow-ups",
)
async def list_followups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FollowupSuggestion]:
    """
    Return all pending follow-up suggestions for the authenticated user.

    - Only emails older than followup_threshold days with is_replied=False (Req 7.1).
    - Excludes snoozed, resolved, and sent follow-ups (Req 7.2).
    - At most one pending follow-up per email (Req 7.3).
    - Sorted by sent_at ascending (Req 7.4).

    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    user_id = str(current_user.id)
    agent = _make_followup_agent(db)

    suggestions = await agent.check_pending_followups(user_id, db)

    logger.info(
        "GET /followups — user=%s, count=%d",
        user_id,
        len(suggestions),
    )
    return suggestions


@router.post(
    "/{followup_id}/snooze",
    status_code=200,
    summary="Snooze a follow-up until a specified datetime",
)
async def snooze_followup(
    followup_id: UUID,
    body: SnoozeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Snooze the specified follow-up until the given datetime.

    The follow-up will be suppressed from results until the snooze period
    has elapsed.

    Raises HTTP 404 if the follow-up record is not found.

    Requirements: 7.6
    """
    user_id = str(current_user.id)
    agent = _make_followup_agent(db)

    await agent.snooze_followup(
        followup_id=str(followup_id),
        snooze_until=body.until,
        db=db,
    )

    logger.info(
        "POST /followups/%s/snooze — user=%s, until=%s",
        followup_id,
        user_id,
        body.until.isoformat(),
    )
    return {"status": "snoozed"}


@router.post(
    "/{followup_id}/resolve",
    status_code=200,
    summary="Resolve a follow-up",
)
async def resolve_followup(
    followup_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Mark the specified follow-up as resolved.

    Resolved follow-ups are excluded from all future follow-up checks.

    Raises HTTP 404 if the follow-up record is not found.

    Requirements: 7.7
    """
    user_id = str(current_user.id)
    agent = _make_followup_agent(db)

    await agent.resolve_followup(
        followup_id=str(followup_id),
        db=db,
    )

    logger.info(
        "POST /followups/%s/resolve — user=%s",
        followup_id,
        user_id,
    )
    return {"status": "resolved"}


@router.post(
    "/{followup_id}/generate-draft",
    response_model=ReplyDraft,
    summary="Generate a contextual follow-up draft",
)
async def generate_followup_draft(
    followup_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReplyDraft:
    """
    Generate a contextual follow-up draft for the specified follow-up.

    Uses the DecisionEngine to produce a draft message tailored to the
    original email's content and the number of days elapsed.

    Raises HTTP 404 if the follow-up or its associated email is not found.

    Requirements: 7.5
    """
    user_id = str(current_user.id)
    agent = _make_followup_agent(db)

    draft_text = await agent.generate_followup_draft(
        followup_id=str(followup_id),
        db=db,
    )

    # Wrap the draft text in a ReplyDraft response
    draft = ReplyDraft(
        id=uuid.uuid4(),
        email_id=followup_id,  # use followup_id as a proxy; caller can resolve email_id
        draft_text=draft_text,
        status="pending",
    )

    logger.info(
        "POST /followups/%s/generate-draft — user=%s",
        followup_id,
        user_id,
    )
    return draft
