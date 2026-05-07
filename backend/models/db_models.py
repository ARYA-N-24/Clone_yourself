"""
SQLAlchemy 2.0 ORM mapped classes for the Clone Yourself Platform.

All seven tables are modelled using DeclarativeBase, Mapped[T] typed annotations,
and mapped_column() definitions that match database/schema.sql exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP, Time


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    picture_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        "UserPreference", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    emails: Mapped[list["Email"]] = relationship(
        "Email", back_populates="user", cascade="all, delete-orphan"
    )
    reply_drafts: Mapped[list["ReplyDraft"]] = relationship(
        "ReplyDraft", back_populates="user", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(
        "CalendarEvent", back_populates="user", cascade="all, delete-orphan"
    )
    followups: Mapped[list["Followup"]] = relationship(
        "Followup", back_populates="user", cascade="all, delete-orphan"
    )
    analytics_events: Mapped[list["AnalyticsEvent"]] = relationship(
        "AnalyticsEvent", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ---------------------------------------------------------------------------
# oauth_tokens
# ---------------------------------------------------------------------------

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Stored encrypted at rest
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="oauth_tokens")

    def __repr__(self) -> str:
        return f"<OAuthToken id={self.id} user_id={self.user_id}>"


# ---------------------------------------------------------------------------
# user_preferences
# ---------------------------------------------------------------------------

class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tone: Mapped[str] = mapped_column(Text, nullable=False, server_default="casual")
    working_hours_start: Mapped[time] = mapped_column(
        Time, nullable=False, server_default="09:00"
    )
    working_hours_end: Mapped[time] = mapped_column(
        Time, nullable=False, server_default="18:00"
    )
    # INT[] NOT NULL DEFAULT '{1,2,3,4,5}'
    working_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{1,2,3,4,5}"
    )
    meeting_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30"
    )
    followup_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    execution_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="suggest"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreference user_id={self.user_id} tone={self.tone!r}>"


# ---------------------------------------------------------------------------
# emails
# ---------------------------------------------------------------------------

class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (UniqueConstraint("user_id", "gmail_id", name="uq_emails_user_gmail"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    gmail_id: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    classification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_replied: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    embedding_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="emails")
    reply_drafts: Mapped[list["ReplyDraft"]] = relationship(
        "ReplyDraft", back_populates="email", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(
        "CalendarEvent",
        back_populates="source_email",
        foreign_keys="CalendarEvent.source_email_id",
    )
    followups: Mapped[list["Followup"]] = relationship(
        "Followup",
        back_populates="email",
        cascade="all, delete-orphan",
        foreign_keys="Followup.email_id",
    )

    def __repr__(self) -> str:
        return f"<Email id={self.id} gmail_id={self.gmail_id!r}>"


# ---------------------------------------------------------------------------
# reply_drafts
# ---------------------------------------------------------------------------

class ReplyDraft(Base):
    __tablename__ = "reply_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=True,
    )
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="reply_drafts")
    email: Mapped[Optional["Email"]] = relationship("Email", back_populates="reply_drafts")
    followups: Mapped[list["Followup"]] = relationship(
        "Followup",
        back_populates="draft",
        foreign_keys="Followup.draft_id",
    )

    def __repr__(self) -> str:
        return f"<ReplyDraft id={self.id} status={self.status!r}>"


# ---------------------------------------------------------------------------
# calendar_events
# ---------------------------------------------------------------------------

class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    gcal_event_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    attendees: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    source_email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id"),
        nullable=True,
    )
    created_by_ai: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="calendar_events")
    source_email: Mapped[Optional["Email"]] = relationship(
        "Email",
        back_populates="calendar_events",
        foreign_keys=[source_email_id],
    )

    def __repr__(self) -> str:
        return f"<CalendarEvent id={self.id} title={self.title!r}>"


# ---------------------------------------------------------------------------
# followups
# ---------------------------------------------------------------------------

class Followup(Base):
    __tablename__ = "followups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    snooze_until: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reply_drafts.id"),
        nullable=True,
    )
    detected_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="followups")
    email: Mapped[Optional["Email"]] = relationship(
        "Email",
        back_populates="followups",
        foreign_keys=[email_id],
    )
    draft: Mapped[Optional["ReplyDraft"]] = relationship(
        "ReplyDraft",
        back_populates="followups",
        foreign_keys=[draft_id],
    )

    def __repr__(self) -> str:
        return f"<Followup id={self.id} status={self.status!r}>"


# ---------------------------------------------------------------------------
# analytics_events
# ---------------------------------------------------------------------------

class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    time_saved_min: Mapped[Optional[float]] = mapped_column(
        Float, server_default="0", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="analytics_events")

    def __repr__(self) -> str:
        return f"<AnalyticsEvent id={self.id} event_type={self.event_type!r}>"
