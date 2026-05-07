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


# ---------------------------------------------------------------------------
# Demo seed data
# ---------------------------------------------------------------------------

import uuid as _uuid
from datetime import datetime, timedelta, timezone as _tz


def seed_demo_data(db_session) -> dict:  # type: ignore[type-arg]
    """
    Insert deterministic demo data into the database.

    Inserts:
    - 1 demo user with preferences
    - 5 sample emails (urgent/normal/low, including a meeting-request)
    - 2 pending reply drafts
    - 3 calendar events
    - 2 pending followups
    - 10 analytics events spanning the past week

    Args:
        db_session: A synchronous SQLAlchemy Session.

    Returns:
        A summary dict with counts of inserted records.
    """
    from backend.models.db_models import (
        User,
        UserPreference,
        Email,
        ReplyDraft,
        CalendarEvent,
        Followup,
        AnalyticsEvent,
    )

    now = datetime.now(tz=_tz.utc)

    # ── Demo user ────────────────────────────────────────────────────────────
    demo_user_id = _uuid.UUID("dddddddd-0000-0000-0000-000000000001")

    existing_user = db_session.get(User, demo_user_id)
    if existing_user is None:
        demo_user = User(
            id=demo_user_id,
            email="demo@cloneyourself.ai",
            name="Demo User",
            picture_url=None,
        )
        db_session.add(demo_user)

    # ── User preferences ─────────────────────────────────────────────────────
    from datetime import time as _time

    existing_prefs = db_session.get(UserPreference, demo_user_id)
    if existing_prefs is None:
        prefs = UserPreference(
            user_id=demo_user_id,
            tone="casual",
            working_hours_start=_time(9, 0),
            working_hours_end=_time(18, 0),
            working_days=[1, 2, 3, 4, 5],
            meeting_duration=30,
            followup_threshold=3,
            execution_mode="suggest",
        )
        db_session.add(prefs)

    # ── Emails ───────────────────────────────────────────────────────────────
    email_ids = [
        _uuid.UUID(f"eeeeeeee-0000-0000-0000-00000000000{i}") for i in range(1, 6)
    ]

    email_data = [
        dict(
            id=email_ids[0],
            user_id=demo_user_id,
            gmail_id="demo_gmail_001",
            thread_id="demo_thread_001",
            subject="Can we meet next week to discuss the Q3 roadmap?",
            sender="alice.johnson@example.com",
            recipient="demo@cloneyourself.ai",
            body_text="Hi, I'd love to find time next week to go over the Q3 roadmap. Would Monday or Tuesday afternoon work?",
            received_at=now - timedelta(hours=2),
            classification="urgent",
            category="meeting-request",
            is_replied=False,
        ),
        dict(
            id=email_ids[1],
            user_id=demo_user_id,
            gmail_id="demo_gmail_002",
            thread_id="demo_thread_002",
            subject="Action required: Review and sign the updated NDA",
            sender="legal@partnerco.com",
            recipient="demo@cloneyourself.ai",
            body_text="Please review the attached NDA and return a signed copy by end of business Friday.",
            received_at=now - timedelta(hours=5),
            classification="normal",
            category="action-required",
            is_replied=False,
        ),
        dict(
            id=email_ids[2],
            user_id=demo_user_id,
            gmail_id="demo_gmail_003",
            thread_id="demo_thread_003",
            subject="This week in AI: GPT-5 rumours and more",
            sender="newsletter@aiweekly.io",
            recipient="demo@cloneyourself.ai",
            body_text="Welcome to this week's AI Weekly digest! Highlights from NeurIPS 2024 workshops.",
            received_at=now - timedelta(hours=8),
            classification="low",
            category="info",
            is_replied=False,
        ),
        dict(
            id=email_ids[3],
            user_id=demo_user_id,
            gmail_id="demo_gmail_004",
            thread_id="demo_thread_004",
            subject="Follow up on the investor deck",
            sender="investor@venturecap.com",
            recipient="demo@cloneyourself.ai",
            body_text="Just checking in on the seed round deck. Any updates on the timeline?",
            received_at=now - timedelta(days=1),
            classification="urgent",
            category="action-required",
            is_replied=False,
        ),
        dict(
            id=email_ids[4],
            user_id=demo_user_id,
            gmail_id="demo_gmail_005",
            thread_id="demo_thread_005",
            subject="Your monthly SaaS subscription receipt",
            sender="billing@saastool.com",
            recipient="demo@cloneyourself.ai",
            body_text="Thank you for your payment of $49.00 for the Pro plan. Your next billing date is August 15.",
            received_at=now - timedelta(days=2),
            classification="low",
            category="info",
            is_replied=True,
        ),
    ]

    for ed in email_data:
        if db_session.get(Email, ed["id"]) is None:
            db_session.add(Email(**ed))

    # ── Reply drafts ─────────────────────────────────────────────────────────
    draft_ids = [
        _uuid.UUID(f"ffffffff-0000-0000-0000-00000000000{i}") for i in range(1, 3)
    ]

    draft_data = [
        dict(
            id=draft_ids[0],
            user_id=demo_user_id,
            email_id=email_ids[0],
            draft_text=(
                "Hi Alice,\n\nMonday afternoon works great for me! "
                "How about 2pm? I'll send a calendar invite.\n\nBest,\nDemo"
            ),
            status="pending",
        ),
        dict(
            id=draft_ids[1],
            user_id=demo_user_id,
            email_id=email_ids[1],
            draft_text=(
                "Hi,\n\nThank you for sending over the NDA. "
                "I'll review it today and return the signed copy by Friday.\n\nBest regards,\nDemo"
            ),
            status="pending",
        ),
    ]

    for dd in draft_data:
        if db_session.get(ReplyDraft, dd["id"]) is None:
            db_session.add(ReplyDraft(**dd))

    # ── Calendar events ───────────────────────────────────────────────────────
    cal_ids = [
        _uuid.UUID(f"cccccccc-0000-0000-0000-00000000000{i}") for i in range(1, 4)
    ]

    cal_data = [
        dict(
            id=cal_ids[0],
            user_id=demo_user_id,
            gcal_event_id="demo_gcal_001",
            title="Daily Stand-up",
            start_time=now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1),
            end_time=now.replace(hour=9, minute=15, second=0, microsecond=0) + timedelta(days=1),
            attendees=["demo@cloneyourself.ai", "alice.johnson@example.com"],
            source_email_id=None,
            created_by_ai=False,
        ),
        dict(
            id=cal_ids[1],
            user_id=demo_user_id,
            gcal_event_id="demo_gcal_002",
            title="Q3 Roadmap Planning — Alice & Demo",
            start_time=now.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=3),
            end_time=now.replace(hour=14, minute=30, second=0, microsecond=0) + timedelta(days=3),
            attendees=["demo@cloneyourself.ai", "alice.johnson@example.com"],
            source_email_id=email_ids[0],
            created_by_ai=True,
        ),
        dict(
            id=cal_ids[2],
            user_id=demo_user_id,
            gcal_event_id="demo_gcal_003",
            title="Investor Update Call",
            start_time=now.replace(hour=16, minute=0, second=0, microsecond=0) + timedelta(days=5),
            end_time=now.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=5),
            attendees=["demo@cloneyourself.ai", "investor@venturecap.com"],
            source_email_id=None,
            created_by_ai=False,
        ),
    ]

    for cd in cal_data:
        if db_session.get(CalendarEvent, cd["id"]) is None:
            db_session.add(CalendarEvent(**cd))

    # ── Followups ─────────────────────────────────────────────────────────────
    followup_ids = [
        _uuid.UUID(f"bbbbbbbb-0000-0000-0000-00000000000{i}") for i in range(1, 3)
    ]

    followup_data = [
        dict(
            id=followup_ids[0],
            user_id=demo_user_id,
            email_id=email_ids[3],
            status="pending",
            snooze_until=None,
            draft_id=None,
        ),
        dict(
            id=followup_ids[1],
            user_id=demo_user_id,
            email_id=email_ids[1],
            status="pending",
            snooze_until=None,
            draft_id=None,
        ),
    ]

    for fd in followup_data:
        if db_session.get(Followup, fd["id"]) is None:
            db_session.add(Followup(**fd))

    # ── Analytics events (10 events over the past 7 days) ────────────────────
    analytics_templates = [
        ("reply_sent", 5.0),
        ("reply_sent", 5.0),
        ("reply_sent", 5.0),
        ("event_created", 10.0),
        ("event_created", 10.0),
        ("followup_sent", 5.0),
        ("email_classified", 0.0),
        ("email_classified", 0.0),
        ("email_classified", 0.0),
        ("email_classified", 0.0),
    ]

    for i, (event_type, time_saved) in enumerate(analytics_templates):
        ae_id = _uuid.UUID(f"aaaaaaaa-0000-0000-0000-00000000000{i + 1}")
        if db_session.get(AnalyticsEvent, ae_id) is None:
            db_session.add(
                AnalyticsEvent(
                    id=ae_id,
                    user_id=demo_user_id,
                    event_type=event_type,
                    metadata_={"source": "demo_seed"},
                    time_saved_min=time_saved,
                    created_at=now - timedelta(days=i % 7),
                )
            )

    db_session.commit()

    return {
        "users": 1,
        "emails": len(email_data),
        "reply_drafts": len(draft_data),
        "calendar_events": len(cal_data),
        "followups": len(followup_data),
        "analytics_events": len(analytics_templates),
    }
