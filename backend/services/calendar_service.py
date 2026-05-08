"""
Calendar Service for the Clone Yourself Platform.

Integrates with Google Calendar to read free/busy slots and create events.

Interface:
    - get_free_slots(user_id, date_range) → list[TimeSlot]
    - suggest_meeting_times(user_id, email) → list[MeetingSlot]
    - create_event(user_id, slot, attendees) → CalendarEvent
    - get_upcoming_events(user_id, days) → list[CalendarEvent]

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 13.3
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import openai
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import AnalyticsEvent as AnalyticsEventORM
from models.db_models import CalendarEvent as CalendarEventORM
from models.db_models import OAuthToken, UserPreference
from schemas.pydantic_schemas import (
    AnalyticsEvent,
    CalendarEvent,
    EmailMessage,
    MeetingSlot,
    TimeSlot,
)
from services.decision_engine import DecisionEngine
from utils.token_encryption import decrypt_token
from services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DateRange dataclass
# ---------------------------------------------------------------------------


@dataclass
class DateRange:
    """A half-open time interval [start, end)."""

    start: datetime
    end: datetime


# ---------------------------------------------------------------------------
# CalendarService
# ---------------------------------------------------------------------------


class CalendarService:
    """
    Integrates with Google Calendar to read free/busy slots and create events.

    Args:
        session: SQLAlchemy AsyncSession for database operations.
        decision_engine: DecisionEngine for AI-ranked meeting slot suggestions.
        openai_client: openai.OpenAI (sync) client (reserved for future use).
    """

    def __init__(
        self,
        session: AsyncSession,
        decision_engine: DecisionEngine,
        openai_client: openai.OpenAI,
        analytics_service: AnalyticsService,
    ) -> None:
        self._session = session
        self._decision = decision_engine
        self._openai = openai_client
        self._analytics = analytics_service
        # Tracks whether the last get_free_slots call used mock data
        self._last_source: str = "calendar"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_oauth_token(self, user_id: str) -> tuple[str, str, datetime]:
        """
        Retrieve and decrypt the user's OAuth access and refresh tokens.

        Args:
            user_id: UUID string of the user.

        Returns:
            Tuple of (access_token, refresh_token, token_expiry).

        Raises:
            HTTPException(401): If no OAuth token is found for the user.
        """
        user_uuid = UUID(user_id)
        stmt = (
            select(OAuthToken)
            .where(OAuthToken.user_id == user_uuid)
            .order_by(OAuthToken.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        token_row = result.scalar_one_or_none()

        if token_row is None:
            raise HTTPException(status_code=401, detail="No OAuth token found for user.")

        access_token = decrypt_token(token_row.access_token)
        refresh_token = decrypt_token(token_row.refresh_token)
        token_expiry = token_row.token_expiry
        if token_expiry and token_expiry.tzinfo is not None:
            # google-auth expects a naive UTC datetime to compare with datetime.utcnow()
            token_expiry = token_expiry.replace(tzinfo=None)
        return access_token, refresh_token, token_expiry

    def _build_calendar_client(self, access_token: str, refresh_token: str, token_expiry: datetime):
        """
        Build a Google Calendar API client using the user's OAuth credentials.

        Args:
            access_token: Decrypted OAuth access token.
            refresh_token: Decrypted OAuth refresh token.
            token_expiry: Token expiry datetime.

        Returns:
            A Google API client resource for the Calendar v3 API.
        """
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
            expiry=token_expiry,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    async def _get_user_preferences(self, user_id: str) -> UserPreference:
        """
        Retrieve user preferences from the database.

        Returns a UserPreference ORM object with defaults if none found.

        Args:
            user_id: UUID string of the user.

        Returns:
            UserPreference ORM instance (real or default).
        """
        user_uuid = UUID(user_id)
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await self._session.execute(stmt)
        pref_row = result.scalar_one_or_none()

        if pref_row is None:
            # Return a default preference object without persisting it
            from datetime import time

            default_pref = UserPreference()
            default_pref.user_id = user_uuid
            default_pref.working_hours_start = time(9, 0)
            default_pref.working_hours_end = time(18, 0)
            default_pref.working_days = [1, 2, 3, 4, 5]
            default_pref.meeting_duration = 30
            return default_pref

        return pref_row

    @staticmethod
    async def _fetch_calendar_events(
        calendar_client: Any,
        date_range: DateRange,
    ) -> list[dict]:
        """
        Fetch events from Google Calendar for the given date range.

        Args:
            calendar_client: Google Calendar API client resource.
            date_range: DateRange specifying start and end.

        Returns:
            List of event dicts from the Calendar API.
        """
        time_min = date_range.start.astimezone(timezone.utc).isoformat()
        time_max = date_range.end.astimezone(timezone.utc).isoformat()

        req = calendar_client.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        events_result = await asyncio.to_thread(req.execute)
        return events_result.get("items", [])

    @staticmethod
    def _overlaps(candidate: TimeSlot, event: dict) -> bool:
        """
        Check whether a candidate TimeSlot overlaps with a Google Calendar event.

        Args:
            candidate: The TimeSlot to check.
            event: A Google Calendar event dict with 'start' and 'end' keys.

        Returns:
            True if there is any overlap, False otherwise.
        """
        start_info = event.get("start", {})
        end_info = event.get("end", {})

        # Handle both dateTime (timed events) and date (all-day events)
        event_start_str = start_info.get("dateTime") or start_info.get("date")
        event_end_str = end_info.get("dateTime") or end_info.get("date")

        if not event_start_str or not event_end_str:
            return False

        try:
            # Parse ISO 8601 strings; all-day events use date-only format
            if "T" in event_start_str:
                event_start = datetime.fromisoformat(event_start_str)
            else:
                # All-day event: treat as midnight UTC
                event_start = datetime.fromisoformat(event_start_str + "T00:00:00+00:00")

            if "T" in event_end_str:
                event_end = datetime.fromisoformat(event_end_str)
            else:
                event_end = datetime.fromisoformat(event_end_str + "T00:00:00+00:00")
        except ValueError:
            logger.warning("Could not parse event times: %r / %r", event_start_str, event_end_str)
            return False

        # Ensure both are timezone-aware for comparison
        if candidate.start.tzinfo is None:
            cand_start = candidate.start.replace(tzinfo=timezone.utc)
            cand_end = candidate.end.replace(tzinfo=timezone.utc)
        else:
            cand_start = candidate.start
            cand_end = candidate.end

        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=timezone.utc)
        if event_end.tzinfo is None:
            event_end = event_end.replace(tzinfo=timezone.utc)

        # Overlap: not (cand_end <= event_start or cand_start >= event_end)
        return not (cand_end <= event_start or cand_start >= event_end)

    def _generate_mock_slots(
        self,
        date_range: DateRange,
        prefs: UserPreference,
    ) -> list[TimeSlot]:
        """
        Generate mock free slots from user preferences when Calendar API is unavailable.

        Applies the same free-slot algorithm but without checking existing events.

        Args:
            date_range: DateRange to generate slots for.
            prefs: UserPreference ORM instance.

        Returns:
            List of TimeSlot objects sorted ascending by start time.
        """
        from datetime import time as dt_time

        working_hours_start: dt_time = prefs.working_hours_start
        working_hours_end: dt_time = prefs.working_hours_end
        working_days: list[int] = prefs.working_days or [1, 2, 3, 4, 5]
        meeting_duration: int = prefs.meeting_duration or 30

        free_slots: list[TimeSlot] = []
        current_day = date_range.start.date()
        end_day = date_range.end.date()

        while current_day <= end_day:
            day_of_week = current_day.isoweekday()  # 1=Mon, 7=Sun

            if day_of_week in working_days:
                # Use UTC for mock slots
                slot_start = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    working_hours_start.hour,
                    working_hours_start.minute,
                    tzinfo=timezone.utc,
                )
                day_end = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    working_hours_end.hour,
                    working_hours_end.minute,
                    tzinfo=timezone.utc,
                )
                slot_end = slot_start + timedelta(minutes=meeting_duration)

                while slot_end <= day_end:
                    free_slots.append(TimeSlot(start=slot_start, end=slot_end))
                    slot_start = slot_start + timedelta(minutes=30)
                    slot_end = slot_start + timedelta(minutes=meeting_duration)

            current_day += timedelta(days=1)

        return sorted(free_slots, key=lambda s: s.start)

    async def _record_analytics_event(
        self,
        user_id: str,
        event_type: str,
        metadata: dict | None = None,
        time_saved_min: float = 0.0,
    ) -> None:
        """
        Record an analytics event in the database.

        Failures are logged but do not propagate.

        Args:
            user_id: UUID string of the user.
            event_type: Analytics event type string.
            metadata: Optional metadata dict.
            time_saved_min: Estimated time saved in minutes.
        """
        try:
            user_uuid = UUID(user_id)
            orm_event = AnalyticsEventORM(
                id=uuid.uuid4(),
                user_id=user_uuid,
                event_type=event_type,
                metadata_=metadata,
                time_saved_min=time_saved_min,
                created_at=datetime.utcnow(),
            )
            self._session.add(orm_event)
            await self._session.commit()
            logger.debug("Recorded analytics event '%s' for user %s.", event_type, user_id)
        except Exception as exc:
            logger.warning("Failed to record analytics event '%s': %s", event_type, exc)

    # ------------------------------------------------------------------
    # get_free_slots
    # ------------------------------------------------------------------

    async def get_free_slots(
        self, user_id: str, date_range: DateRange
    ) -> list[TimeSlot]:
        """
        Return free time slots within the date range, filtered by user preferences.

        Retrieves user preferences (working hours, working days, meeting duration)
        and fetches existing Google Calendar events. Generates candidate slots with
        30-minute granularity and filters out any that overlap with existing events.

        Falls back to mock slots (generated from preferences only) if the Calendar
        API is unavailable. Sets ``self._last_source`` to ``"calendar"`` or
        ``"mock"`` accordingly.

        Args:
            user_id: UUID string of the user.
            date_range: DateRange specifying the window to search.

        Returns:
            List of non-overlapping TimeSlot objects sorted ascending by start time.

        Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 13.3
        """
        from datetime import time as dt_time

        prefs = await self._get_user_preferences(user_id)

        working_hours_start: dt_time = prefs.working_hours_start
        working_hours_end: dt_time = prefs.working_hours_end
        working_days: list[int] = prefs.working_days or [1, 2, 3, 4, 5]
        meeting_duration: int = prefs.meeting_duration or 30

        # Attempt to fetch real calendar events
        existing_events: list[dict] = []
        use_mock = False

        try:
            access_token, refresh_token, token_expiry = await self._get_oauth_token(user_id)
            calendar_client = self._build_calendar_client(access_token, refresh_token, token_expiry)
            existing_events = await self._fetch_calendar_events(calendar_client, date_range)
            self._last_source = "calendar"
        except Exception as exc:
            logger.error(
                "Calendar API unavailable for user %s (%s); raising error instead of mock slots.",
                user_id,
                exc,
            )
            raise HTTPException(status_code=503, detail="Google Calendar API is unavailable. Please check your Google OAuth connection.") from exc

        # --- Free slot algorithm ---
        free_slots: list[TimeSlot] = []
        current_day = date_range.start.date()
        end_day = date_range.end.date()

        while current_day <= end_day:
            day_of_week = current_day.isoweekday()  # 1=Mon, 7=Sun

            if day_of_week in working_days:
                # Determine timezone: use date_range.start's tz if available, else UTC
                tz = date_range.start.tzinfo or timezone.utc

                slot_start = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    working_hours_start.hour,
                    working_hours_start.minute,
                    tzinfo=tz,
                )
                day_end = datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    working_hours_end.hour,
                    working_hours_end.minute,
                    tzinfo=tz,
                )
                slot_end = slot_start + timedelta(minutes=meeting_duration)

                while slot_end <= day_end:
                    candidate = TimeSlot(start=slot_start, end=slot_end)

                    # Check for conflicts with existing events
                    has_conflict = False
                    for event in existing_events:
                        if self._overlaps(candidate, event):
                            has_conflict = True
                            break

                    if not has_conflict:
                        free_slots.append(candidate)

                    # Advance by 30-minute granularity
                    slot_start = slot_start + timedelta(minutes=30)
                    slot_end = slot_start + timedelta(minutes=meeting_duration)

            current_day += timedelta(days=1)

        free_slots.sort(key=lambda s: s.start)

        logger.info(
            "Found %d free slots for user %s over %s to %s.",
            len(free_slots),
            user_id,
            date_range.start.date(),
            date_range.end.date(),
        )
        return free_slots

    # ------------------------------------------------------------------
    # suggest_meeting_times
    # ------------------------------------------------------------------

    async def suggest_meeting_times(
        self, user_id: str, email: EmailMessage
    ) -> list[MeetingSlot]:
        """
        Suggest up to 3 AI-ranked meeting times based on the user's free slots.

        Fetches free slots for the next 7 days, then passes them along with the
        email to DecisionEngine.suggest_meeting_slots() for AI ranking.

        Args:
            user_id: UUID string of the user.
            email: The meeting-request email to suggest times for.

        Returns:
            Up to 3 MeetingSlot objects ranked by confidence score.

        Requirements: 6.6, 6.7
        """
        now = datetime.now(tz=timezone.utc)
        date_range = DateRange(start=now, end=now + timedelta(days=7))

        free_slots = await self.get_free_slots(user_id, date_range)

        meeting_slots = await self._decision.suggest_meeting_slots(email, free_slots)

        # Return top 3
        return meeting_slots[:3]

    # ------------------------------------------------------------------
    # create_event
    # ------------------------------------------------------------------

    async def create_event(
        self,
        user_id: str,
        slot: MeetingSlot,
        attendees: list[str],
        email_id: str | None = None,
    ) -> CalendarEvent:
        """
        Create a Google Calendar event for the given meeting slot.

        Builds a Calendar event from the slot and attendees, inserts it via the
        Calendar API, persists it to the calendar_events table, and records an
        event_created analytics event with time_saved_min=10.

        Args:
            user_id: UUID string of the user.
            slot: MeetingSlot containing the time window and reason.
            attendees: List of attendee email addresses.
            email_id: Optional UUID of the email that triggered this meeting.

        Returns:
            CalendarEvent Pydantic model for the created event.

        Raises:
            HTTPException(503): If the Calendar API call fails.

        Requirements: 6.8, 6.9
        """
        user_uuid = UUID(user_id)
        email_uuid = UUID(email_id) if email_id else None

        # Build the event body
        title = slot.reason or "Meeting"
        start_dt = slot.slot.start
        end_dt = slot.slot.end

        # Ensure timezone-aware datetimes for the API
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        attendee_list = [{"email": addr} for addr in attendees]

        event_body = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
            "attendees": attendee_list,
        }

        gcal_event_id: str | None = None

        try:
            access_token, refresh_token, token_expiry = await self._get_oauth_token(user_id)
            calendar_client = self._build_calendar_client(access_token, refresh_token, token_expiry)

            send_updates_val = "all" if attendee_list else "none"
            insert_req = (
                calendar_client.events()
                .insert(calendarId="primary", body=event_body, sendUpdates=send_updates_val)
            )
            created = await asyncio.to_thread(insert_req.execute)
            gcal_event_id = created.get("id")
            logger.info(
                "Created Google Calendar event %s for user %s.", gcal_event_id, user_id
            )

        except Exception as exc:
            logger.error(
                "Calendar API error while creating event for user %s: %s", user_id, exc
            )
            raise HTTPException(
                status_code=503,
                detail="Google Calendar API is unavailable. Please try again later.",
            ) from exc

        # Persist to calendar_events table
        event_id = uuid.uuid4()
        now_utc = datetime.now(tz=timezone.utc)

        orm_event = CalendarEventORM(
            id=event_id,
            user_id=user_uuid,
            gcal_event_id=gcal_event_id,
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            attendees=attendees,
            source_email_id=email_uuid,
            created_by_ai=True,
            created_at=now_utc,
        )
        self._session.add(orm_event)

        # Mark the original email as replied/processed
        if email_uuid:
            from models.db_models import EmailORM
            stmt = select(EmailORM).where(EmailORM.id == email_uuid)
            result = await self._session.execute(stmt)
            email_row = result.scalar_one_or_none()
            if email_row:
                email_row.is_replied = True

        await self._session.commit()
        await self._session.refresh(orm_event)

        logger.info(
            "Persisted calendar event %s for user %s.", event_id, user_id
        )

        # Record analytics event
        from schemas.pydantic_schemas import AnalyticsEvent
        await self._analytics.record_event(
            user_id=user_id,
            event=AnalyticsEvent(
                id=uuid.uuid4(),
                user_id=user_uuid,
                event_type="event_created",
                metadata_={"event_id": str(event_id), "gcal_event_id": gcal_event_id},
                time_saved_min=10.0,
                created_at=now_utc,
            ),
        )

        return CalendarEvent(
            id=event_id,
            user_id=user_uuid,
            gcal_event_id=gcal_event_id,
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            attendees=attendees,
            source_email_id=email_uuid,
            created_by_ai=True,
            created_at=now_utc,
        )

    # ------------------------------------------------------------------
    # get_upcoming_events
    # ------------------------------------------------------------------

    async def get_upcoming_events(
        self, user_id: str, days: int = 7
    ) -> list[CalendarEvent]:
        """
        Fetch upcoming calendar events from the database for the next N days.

        Queries the calendar_events table for events whose start_time falls
        within [now, now + days].

        Args:
            user_id: UUID string of the user.
            days: Number of days ahead to look (default 7).

        Returns:
            List of CalendarEvent Pydantic models sorted by start_time ascending.

        Requirements: 6.3, 6.4
        """
        user_uuid = UUID(user_id)
        now = datetime.now(tz=timezone.utc)
        cutoff = now + timedelta(days=days)

        stmt = (
            select(CalendarEventORM)
            .where(
                CalendarEventORM.user_id == user_uuid,
                CalendarEventORM.start_time >= now,
                CalendarEventORM.start_time <= cutoff,
            )
            .order_by(CalendarEventORM.start_time.asc())
        )

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        events = [CalendarEvent.model_validate(row) for row in rows]

        logger.info(
            "Fetched %d upcoming events for user %s (next %d days).",
            len(events),
            user_id,
            days,
        )
        return events
