"""
Pydantic v2 models for the Clone Yourself Platform.

All models use ConfigDict(from_attributes=True) where ORM compatibility is needed
(i.e., models that map directly to SQLAlchemy ORM objects). Pure request/response
models and composite models do not need ORM compatibility.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Core domain models (ORM-compatible)
# ---------------------------------------------------------------------------


class User(BaseModel):
    """Represents an authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    picture_url: Optional[str] = None


class UserPreferences(BaseModel):
    """User behavioural preferences stored in user_preferences table."""

    model_config = ConfigDict(from_attributes=True)

    tone: Literal["formal", "casual"] = "casual"
    working_hours_start: time = time(9, 0)
    working_hours_end: time = time(18, 0)
    working_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    meeting_duration: int = 30
    followup_threshold: int = 3
    execution_mode: Literal["suggest", "approval", "auto"] = "suggest"


class EmailMessage(BaseModel):
    """Represents a single email fetched from Gmail and stored in the emails table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gmail_id: str
    thread_id: str
    subject: Optional[str] = None
    sender: str
    recipient: str
    body_text: Optional[str] = None
    received_at: datetime
    classification: Optional[Literal["urgent", "normal", "low"]] = None
    category: Optional[str] = None
    is_replied: bool = False


class ReplyDraft(BaseModel):
    """An AI-generated reply draft stored in the reply_drafts table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_id: UUID
    draft_text: str
    status: Literal["pending", "approved", "sent", "discarded"] = "pending"


# ---------------------------------------------------------------------------
# Calendar models
# ---------------------------------------------------------------------------


class TimeSlot(BaseModel):
    """A contiguous time window (start, end)."""

    start: datetime
    end: datetime


class MeetingSlot(BaseModel):
    """An AI-ranked meeting time suggestion with a confidence score and reason."""

    slot: TimeSlot
    confidence_score: float = Field(ge=0.0, le=1.0)
    reason: str


# ---------------------------------------------------------------------------
# Analytics models (ORM-compatible)
# ---------------------------------------------------------------------------


class AnalyticsStats(BaseModel):
    """Aggregated productivity metrics for the dashboard."""

    model_config = ConfigDict(from_attributes=True)

    actions_automated: int
    time_saved_minutes: float
    emails_classified: int
    replies_sent: int
    events_created: int


class AnalyticsEvent(BaseModel):
    """A single analytics event stored in the analytics_events table."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: UUID
    event_type: Literal[
        "reply_sent", "event_created", "followup_sent", "email_classified"
    ]
    metadata: Optional[dict[str, Any]] = Field(None, alias="metadata_")
    time_saved_min: float = 0.0
    created_at: datetime


# ---------------------------------------------------------------------------
# Dashboard / brief models
# ---------------------------------------------------------------------------


class DashboardPayload(BaseModel):
    """Aggregated payload returned by GET /dashboard."""

    priority_emails: list[EmailMessage]
    pending_replies: list[ReplyDraft]
    suggested_actions: list[str]
    followup_count: int
    analytics: AnalyticsStats


class DailyBrief(BaseModel):
    """AI-generated daily brief with exactly 3 urgent items, 2 followups, 1 risk."""

    urgent_items: list[str]  # exactly 3
    followups: list[str]     # exactly 2
    risk: str                # exactly 1 non-empty string
    generated_at: datetime


# ---------------------------------------------------------------------------
# Style / context models (used internally by Decision Engine)
# ---------------------------------------------------------------------------


class StyleContext(BaseModel):
    """Writing style context passed to the Decision Engine for reply generation."""

    tone: Literal["formal", "casual"]
    similar_emails: list[EmailMessage] = Field(default_factory=list)


class BriefContext(BaseModel):
    """Context bundle passed to the Decision Engine for daily brief generation."""

    urgent_emails: list[EmailMessage]
    pending_followups: list["FollowupSuggestion"]
    upcoming_events: list["CalendarEvent"]
    analytics_stats: AnalyticsStats


# ---------------------------------------------------------------------------
# Follow-up model (ORM-compatible)
# ---------------------------------------------------------------------------


class FollowupSuggestion(BaseModel):
    """A follow-up suggestion surfaced by the Follow-up Agent."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_id: UUID
    sender: str
    subject: Optional[str] = None
    sent_at: datetime
    days_elapsed: int
    draft_text: str
    status: Literal["pending", "snoozed", "resolved", "sent"] = "pending"
    snooze_until: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Calendar event model (ORM-compatible)
# ---------------------------------------------------------------------------


class CalendarEvent(BaseModel):
    """A calendar event stored in the calendar_events table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    gcal_event_id: Optional[str] = None
    title: str
    start_time: datetime
    end_time: datetime
    attendees: Optional[list[str]] = None
    source_email_id: Optional[UUID] = None
    created_by_ai: bool = False
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Auth response model
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """JWT token response returned after successful OAuth callback."""

    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class GenerateReplyRequest(BaseModel):
    """Request body for POST /emails/generate-reply."""

    email_id: UUID


class CalendarSuggestRequest(BaseModel):
    """Request body for POST /calendar/suggest."""

    email_id: UUID


# ---------------------------------------------------------------------------
# Rebuild forward references
# ---------------------------------------------------------------------------

BriefContext.model_rebuild()
