"""
Mock data fallback for the Clone Yourself Platform.

Used when external APIs (Gmail, Google Calendar) are unavailable — e.g. during
local development, demos, or when OAuth tokens have not yet been configured.

All UUIDs are fixed so the data is deterministic across restarts.
All datetimes are timezone-aware (UTC).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.schemas.pydantic_schemas import (
    AnalyticsStats,
    CalendarEvent,
    EmailMessage,
)

# ---------------------------------------------------------------------------
# Helper: fixed UTC datetime
# ---------------------------------------------------------------------------

def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mock emails
# ---------------------------------------------------------------------------

MOCK_EMAILS: list[EmailMessage] = [
    # 1. Urgent meeting-request email
    EmailMessage(
        id=uuid.UUID("11111111-0000-0000-0000-000000000001"),
        gmail_id="mock_gmail_001",
        thread_id="mock_thread_001",
        subject="Can we meet next week to discuss the Q3 roadmap?",
        sender="alice.johnson@example.com",
        recipient="me@example.com",
        body_text=(
            "Hi,\n\n"
            "I'd love to find some time next week to go over the Q3 roadmap together. "
            "There are a few open questions around prioritisation that I think we should "
            "align on before the sprint planning session.\n\n"
            "Would Monday or Tuesday afternoon work for you? Happy to do 30 minutes.\n\n"
            "Best,\nAlice"
        ),
        received_at=_utc(2024, 7, 15, 9, 12),
        classification="urgent",
        category="meeting-request",
        is_replied=False,
    ),
    # 2. Normal action-required email
    EmailMessage(
        id=uuid.UUID("11111111-0000-0000-0000-000000000002"),
        gmail_id="mock_gmail_002",
        thread_id="mock_thread_002",
        subject="Action required: Review and sign the updated NDA",
        sender="legal@partnerco.com",
        recipient="me@example.com",
        body_text=(
            "Hello,\n\n"
            "Please review the attached Non-Disclosure Agreement and return a signed copy "
            "by end of business Friday. This is required before we can proceed with the "
            "partnership onboarding.\n\n"
            "Let me know if you have any questions.\n\n"
            "Regards,\nLegal Team, PartnerCo"
        ),
        received_at=_utc(2024, 7, 15, 11, 45),
        classification="normal",
        category="action-required",
        is_replied=False,
    ),
    # 3. Low-priority newsletter / info email
    EmailMessage(
        id=uuid.UUID("11111111-0000-0000-0000-000000000003"),
        gmail_id="mock_gmail_003",
        thread_id="mock_thread_003",
        subject="This week in AI: GPT-5 rumours, open-source highlights & more",
        sender="newsletter@aiweekly.io",
        recipient="me@example.com",
        body_text=(
            "Welcome to this week's AI Weekly digest!\n\n"
            "• Rumours about GPT-5 capabilities continue to circulate.\n"
            "• Mistral releases a new 7B instruction-tuned model.\n"
            "• Highlights from NeurIPS 2024 workshops.\n\n"
            "Read the full issue at https://aiweekly.io/issues/42\n\n"
            "Unsubscribe | Manage preferences"
        ),
        received_at=_utc(2024, 7, 15, 8, 0),
        classification="low",
        category="info",
        is_replied=False,
    ),
]


# ---------------------------------------------------------------------------
# Mock calendar events
# ---------------------------------------------------------------------------

# A fixed user UUID used as the owner of all mock calendar events.
_MOCK_USER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

MOCK_CALENDAR_EVENTS: list[CalendarEvent] = [
    # 1. Team stand-up (recurring, short)
    CalendarEvent(
        id=uuid.UUID("22222222-0000-0000-0000-000000000001"),
        user_id=_MOCK_USER_ID,
        gcal_event_id="mock_gcal_event_001",
        title="Daily Stand-up",
        start_time=_utc(2024, 7, 16, 9, 0),
        end_time=_utc(2024, 7, 16, 9, 15),
        attendees=[
            "me@example.com",
            "alice.johnson@example.com",
            "bob.smith@example.com",
        ],
        source_email_id=None,
        created_by_ai=False,
        created_at=_utc(2024, 7, 1, 10, 0),
    ),
    # 2. Q3 roadmap planning session (AI-created from meeting-request email)
    CalendarEvent(
        id=uuid.UUID("22222222-0000-0000-0000-000000000002"),
        user_id=_MOCK_USER_ID,
        gcal_event_id="mock_gcal_event_002",
        title="Q3 Roadmap Planning — Alice & Me",
        start_time=_utc(2024, 7, 17, 14, 0),
        end_time=_utc(2024, 7, 17, 14, 30),
        attendees=[
            "me@example.com",
            "alice.johnson@example.com",
        ],
        source_email_id=uuid.UUID("11111111-0000-0000-0000-000000000001"),
        created_by_ai=True,
        created_at=_utc(2024, 7, 15, 9, 30),
    ),
    # 3. Investor update call
    CalendarEvent(
        id=uuid.UUID("22222222-0000-0000-0000-000000000003"),
        user_id=_MOCK_USER_ID,
        gcal_event_id="mock_gcal_event_003",
        title="Investor Update Call — Seed Round",
        start_time=_utc(2024, 7, 18, 16, 0),
        end_time=_utc(2024, 7, 18, 17, 0),
        attendees=[
            "me@example.com",
            "investor@venturecap.com",
            "cfo@example.com",
        ],
        source_email_id=None,
        created_by_ai=False,
        created_at=_utc(2024, 7, 10, 12, 0),
    ),
]


# ---------------------------------------------------------------------------
# Mock analytics stats
# ---------------------------------------------------------------------------

MOCK_ANALYTICS_STATS: AnalyticsStats = AnalyticsStats(
    actions_automated=47,
    time_saved_minutes=215.0,   # ~3.5 hours saved this week
    emails_classified=134,
    replies_sent=31,
    events_created=9,
)
