"""
Follow-up Agent service for the Clone Yourself Platform.

Monitors sent emails for missing replies and surfaces follow-up suggestions.

Interface:
    - check_pending_followups(user_id, db) → list[FollowupSuggestion]
    - snooze_followup(followup_id, snooze_until, db) → None
    - resolve_followup(followup_id, db) → None
    - generate_followup_draft(followup_id, db) → str

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import Email as EmailORM
from models.db_models import Followup as FollowupORM
from models.db_models import UserPreference
from schemas.pydantic_schemas import EmailMessage, FollowupSuggestion
from services.decision_engine import DecisionEngine

logger = logging.getLogger(__name__)


class FollowupAgent:
    """
    Detects unreplied sent emails and manages follow-up lifecycle.

    Args:
        decision_engine: DecisionEngine used to generate follow-up draft text.
    """

    def __init__(self, decision_engine: DecisionEngine) -> None:
        self._decision = decision_engine

    # ------------------------------------------------------------------
    # check_pending_followups
    # ------------------------------------------------------------------

    async def check_pending_followups(
        self, user_id: str, db: AsyncSession
    ) -> list[FollowupSuggestion]:
        """
        Query emails older than followup_threshold days with is_replied = FALSE
        and no active (pending/snoozed) followup. Upsert followup records to
        enforce at-most-one-pending-per-email. Return results sorted by
        sent_at ascending (oldest first).

        Steps:
        1. Load the user's followup_threshold from user_preferences (default 3).
        2. Compute cutoff = NOW() - threshold_days.
        3. Query emails where:
               user_id = :user_id
           AND is_replied = FALSE
           AND received_at < cutoff
           AND no followup with status IN ('pending', 'snoozed', 'resolved', 'sent')
        4. For each qualifying email, upsert a followup record with status='pending'
           (skip if a pending record already exists — at-most-one enforcement).
        5. Call DecisionEngine.suggest_followup() to generate a draft.
        6. Return list sorted by sent_at ascending.

        Args:
            user_id: UUID string of the user.
            db: SQLAlchemy AsyncSession.

        Returns:
            List of FollowupSuggestion objects sorted by sent_at ascending.

        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
        """
        user_uuid = UUID(user_id)

        # Step 1: Load followup_threshold from user_preferences (default 3)
        threshold_days = await self._get_followup_threshold(user_id, db)

        # Step 2: Compute cutoff time
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=threshold_days)

        # Step 3: Query emails older than cutoff with is_replied = FALSE
        # and no active followup (pending, snoozed, resolved, or sent).
        # We use a LEFT JOIN via subquery: exclude emails that have ANY followup
        # with status in ('pending', 'snoozed', 'resolved', 'sent').
        active_statuses = ("pending", "snoozed", "resolved", "sent")

        # Subquery: email IDs that already have an active followup
        active_followup_subq = (
            select(FollowupORM.email_id)
            .where(
                and_(
                    FollowupORM.user_id == user_uuid,
                    FollowupORM.status.in_(active_statuses),
                )
            )
            .scalar_subquery()
        )

        stmt = (
            select(EmailORM)
            .where(
                and_(
                    EmailORM.user_id == user_uuid,
                    EmailORM.is_replied == False,  # noqa: E712
                    EmailORM.received_at < cutoff,
                    EmailORM.id.not_in(active_followup_subq),
                )
            )
            .order_by(EmailORM.received_at.asc())
        )

        result = await db.execute(stmt)
        email_rows = result.scalars().all()

        if not email_rows:
            logger.debug(
                "No pending followup candidates found for user %s.", user_id
            )
            return []

        suggestions: list[FollowupSuggestion] = []

        for email_row in email_rows:
            # Step 4: Upsert followup record with status='pending'
            # At-most-one-pending enforcement: only insert if no pending record exists.
            followup_id = await self._upsert_pending_followup(
                user_uuid=user_uuid,
                email_id=email_row.id,
                db=db,
            )

            if followup_id is None:
                # A pending record already existed — skip to avoid duplicates
                logger.debug(
                    "Skipping email %s: pending followup already exists.", email_row.id
                )
                continue

            # Step 5: Build EmailMessage and generate draft via DecisionEngine
            email_msg = EmailMessage(
                id=email_row.id,
                gmail_id=email_row.gmail_id,
                thread_id=email_row.thread_id,
                subject=email_row.subject,
                sender=email_row.sender,
                recipient=email_row.recipient,
                body_text=email_row.body_text,
                received_at=email_row.received_at,
                classification=email_row.classification,
                category=email_row.category,
                is_replied=email_row.is_replied or False,
            )

            days_elapsed = (now - email_row.received_at).days

            try:
                suggestion = await self._decision.suggest_followup(
                    email_msg, days_elapsed
                )
            except Exception as exc:
                logger.warning(
                    "Failed to generate followup draft for email %s: %s",
                    email_row.id,
                    exc,
                )
                # Provide a minimal fallback suggestion
                suggestion = FollowupSuggestion(
                    id=followup_id,
                    email_id=email_row.id,
                    sender=email_row.sender,
                    subject=email_row.subject,
                    sent_at=email_row.received_at,
                    days_elapsed=days_elapsed,
                    draft_text=(
                        "Hi, just following up on my previous email. "
                        "Please let me know if you have any updates."
                    ),
                    status="pending",
                )

            # Override the suggestion's id with the DB followup record id
            suggestion = suggestion.model_copy(
                update={"id": followup_id, "status": "pending"}
            )
            suggestions.append(suggestion)

        # Step 6: Sort by sent_at ascending (oldest first)
        suggestions.sort(key=lambda s: s.sent_at)

        logger.info(
            "Found %d pending followup(s) for user %s.", len(suggestions), user_id
        )
        return suggestions

    # ------------------------------------------------------------------
    # snooze_followup
    # ------------------------------------------------------------------

    async def snooze_followup(
        self,
        followup_id: str,
        snooze_until: datetime,
        db: AsyncSession,
    ) -> None:
        """
        Update a followup record's status to 'snoozed' and set snooze_until.

        The followup will be suppressed from results until snooze_until has passed.

        Args:
            followup_id: UUID string of the followup record.
            snooze_until: Datetime until which the followup should be suppressed.
            db: SQLAlchemy AsyncSession.

        Raises:
            HTTPException(404): If the followup record is not found.

        Requirements: 7.6
        """
        followup_uuid = UUID(followup_id)

        stmt = select(FollowupORM).where(FollowupORM.id == followup_uuid)
        result = await db.execute(stmt)
        followup_row = result.scalar_one_or_none()

        if followup_row is None:
            raise HTTPException(status_code=404, detail="Followup not found.")

        followup_row.status = "snoozed"
        followup_row.snooze_until = snooze_until
        await db.commit()

        logger.info(
            "Snoozed followup %s until %s.", followup_id, snooze_until.isoformat()
        )

    # ------------------------------------------------------------------
    # resolve_followup
    # ------------------------------------------------------------------

    async def resolve_followup(
        self,
        followup_id: str,
        db: AsyncSession,
    ) -> None:
        """
        Update a followup record's status to 'resolved'.

        Resolved followups are excluded from all future follow-up checks.

        Args:
            followup_id: UUID string of the followup record.
            db: SQLAlchemy AsyncSession.

        Raises:
            HTTPException(404): If the followup record is not found.

        Requirements: 7.7
        """
        followup_uuid = UUID(followup_id)

        stmt = select(FollowupORM).where(FollowupORM.id == followup_uuid)
        result = await db.execute(stmt)
        followup_row = result.scalar_one_or_none()

        if followup_row is None:
            raise HTTPException(status_code=404, detail="Followup not found.")

        followup_row.status = "resolved"
        followup_row.resolved_at = datetime.now(tz=timezone.utc)
        await db.commit()

        logger.info("Resolved followup %s.", followup_id)

    # ------------------------------------------------------------------
    # generate_followup_draft
    # ------------------------------------------------------------------

    async def generate_followup_draft(
        self,
        followup_id: str,
        db: AsyncSession,
    ) -> str:
        """
        Generate a draft reply for the given followup using the DecisionEngine.

        Fetches the followup record and its associated email, then calls
        DecisionEngine.suggest_followup() to produce a contextual draft.

        Args:
            followup_id: UUID string of the followup record.
            db: SQLAlchemy AsyncSession.

        Returns:
            Draft text string for the follow-up message.

        Raises:
            HTTPException(404): If the followup or its associated email is not found.

        Requirements: 7.5
        """
        followup_uuid = UUID(followup_id)

        # Fetch the followup record
        stmt = select(FollowupORM).where(FollowupORM.id == followup_uuid)
        result = await db.execute(stmt)
        followup_row = result.scalar_one_or_none()

        if followup_row is None:
            raise HTTPException(status_code=404, detail="Followup not found.")

        # Fetch the associated email
        email_stmt = select(EmailORM).where(EmailORM.id == followup_row.email_id)
        email_result = await db.execute(email_stmt)
        email_row = email_result.scalar_one_or_none()

        if email_row is None:
            raise HTTPException(
                status_code=404,
                detail="Email associated with followup not found.",
            )

        # Build EmailMessage Pydantic model
        email_msg = EmailMessage(
            id=email_row.id,
            gmail_id=email_row.gmail_id,
            thread_id=email_row.thread_id,
            subject=email_row.subject,
            sender=email_row.sender,
            recipient=email_row.recipient,
            body_text=email_row.body_text,
            received_at=email_row.received_at,
            classification=email_row.classification,
            category=email_row.category,
            is_replied=email_row.is_replied or False,
        )

        now = datetime.now(tz=timezone.utc)
        days_elapsed = (now - email_row.received_at).days

        # Generate draft via DecisionEngine
        try:
            suggestion = await self._decision.suggest_followup(email_msg, days_elapsed)
            draft_text = suggestion.draft_text
        except Exception as exc:
            logger.warning(
                "Failed to generate followup draft for followup %s: %s",
                followup_id,
                exc,
            )
            draft_text = (
                "Hi, just following up on my previous email. "
                "Please let me know if you have any updates."
            )

        logger.info(
            "Generated followup draft for followup %s (email %s).",
            followup_id,
            email_row.id,
        )
        return draft_text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_followup_threshold(
        self, user_id: str, db: AsyncSession
    ) -> int:
        """
        Retrieve the user's followup_threshold from user_preferences.

        Returns 3 (default) if no preferences row exists.

        Args:
            user_id: UUID string of the user.
            db: SQLAlchemy AsyncSession.

        Returns:
            followup_threshold as an integer (minimum 1).
        """
        user_uuid = UUID(user_id)
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await db.execute(stmt)
        pref_row = result.scalar_one_or_none()

        if pref_row is None:
            return 3  # default threshold

        threshold = pref_row.followup_threshold
        # Enforce minimum of 1 day per design precondition
        return max(1, threshold)

    async def _upsert_pending_followup(
        self,
        user_uuid: UUID,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> UUID | None:
        """
        Upsert a followup record with status='pending' for the given email.

        Enforces at-most-one-pending-per-email: if a pending record already
        exists for this email, returns None (caller should skip). Otherwise,
        inserts a new pending record and returns its UUID.

        Args:
            user_uuid: UUID of the user.
            email_id: UUID of the email.
            db: SQLAlchemy AsyncSession.

        Returns:
            UUID of the new followup record, or None if one already existed.

        Requirements: 7.3
        """
        # Check if a pending followup already exists for this email
        existing_stmt = select(FollowupORM).where(
            and_(
                FollowupORM.user_id == user_uuid,
                FollowupORM.email_id == email_id,
                FollowupORM.status == "pending",
            )
        )
        existing_result = await db.execute(existing_stmt)
        existing_row = existing_result.scalar_one_or_none()

        if existing_row is not None:
            # At-most-one enforcement: pending record already exists
            return None

        # Insert a new pending followup record
        new_id = uuid.uuid4()
        new_followup = FollowupORM(
            id=new_id,
            user_id=user_uuid,
            email_id=email_id,
            status="pending",
        )
        db.add(new_followup)
        await db.commit()
        await db.refresh(new_followup)

        logger.debug(
            "Created pending followup %s for email %s.", new_id, email_id
        )
        return new_id
