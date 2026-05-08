"""
Integration test: followup deduplication.

Running check_pending_followups twice for the same email produces exactly
one pending followup record (Property 4).

Requirements: 7.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from models.db_models import Email as EmailORM
from models.db_models import Followup as FollowupORM
from models.db_models import UserPreference
from schemas.pydantic_schemas import FollowupSuggestion
from services.followup_agent import FollowupAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_id() -> str:
    return str(uuid.uuid4())


def _make_email_orm(received_at: datetime) -> MagicMock:
    email = MagicMock(spec=EmailORM)
    email.id = uuid.uuid4()
    email.gmail_id = "gmail-dedup-test"
    email.thread_id = "thread-dedup-test"
    email.subject = "Dedup test email"
    email.sender = "sender@example.com"
    email.recipient = "me@example.com"
    email.body_text = "Please reply to this email."
    email.received_at = received_at
    email.classification = "normal"
    email.category = "info"
    email.is_replied = False
    return email


def _make_pref_row(threshold: int = 3) -> MagicMock:
    pref = MagicMock(spec=UserPreference)
    pref.followup_threshold = threshold
    return pref


def _make_decision_engine(email_id: uuid.UUID = None) -> MagicMock:
    engine = MagicMock()

    async def mock_suggest(email_msg, days_elapsed):
        return FollowupSuggestion(
            id=uuid.uuid4(),
            email_id=email_msg.id,
            sender=email_msg.sender,
            subject=email_msg.subject,
            sent_at=email_msg.received_at,
            days_elapsed=days_elapsed,
            draft_text="Following up on my previous email.",
            status="pending",
        )

    engine.suggest_followup = mock_suggest
    return engine


# ---------------------------------------------------------------------------
# Deduplication test
# ---------------------------------------------------------------------------


class TestFollowupDeduplication:
    """Tests that running check_pending_followups twice produces exactly one pending record."""

    @pytest.mark.asyncio
    async def test_running_twice_produces_one_pending_record(self):
        """
        Property 4: Running check_pending_followups twice for the same email
        produces exactly one pending followup record.
        """
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)
        old_email = _make_email_orm(received_at=now - timedelta(days=5))

        # Track inserted followup records
        inserted_followups: list[FollowupORM] = []

        def mock_add(obj):
            if isinstance(obj, FollowupORM):
                inserted_followups.append(obj)

        # First run: no existing pending followup
        session_run1 = MagicMock()
        session_run1.execute = AsyncMock()
        session_run1.commit = AsyncMock()
        session_run1.refresh = AsyncMock()
        session_run1.add = MagicMock(side_effect=mock_add)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = _make_pref_row(threshold=3)

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [old_email]

        # No existing pending followup on first run
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        session_run1.execute.side_effect = [pref_result, emails_result, no_existing]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        # First run
        suggestions_run1 = await agent.check_pending_followups(user_id, session_run1)

        assert len(suggestions_run1) == 1
        assert len(inserted_followups) == 1

        # Second run: now there IS an existing pending followup
        session_run2 = MagicMock()
        session_run2.execute = AsyncMock()
        session_run2.commit = AsyncMock()
        session_run2.refresh = AsyncMock()
        session_run2.add = MagicMock(side_effect=mock_add)

        pref_result2 = MagicMock()
        pref_result2.scalar_one_or_none.return_value = _make_pref_row(threshold=3)

        # On second run, the email is excluded by the subquery (already has active followup)
        # Simulate this by returning empty emails list
        emails_result2 = MagicMock()
        emails_result2.scalars.return_value.all.return_value = []

        session_run2.execute.side_effect = [pref_result2, emails_result2]

        # Second run
        suggestions_run2 = await agent.check_pending_followups(user_id, session_run2)

        assert len(suggestions_run2) == 0

        # Total inserted followup records should still be exactly 1
        assert len(inserted_followups) == 1

    @pytest.mark.asyncio
    async def test_upsert_skips_when_pending_already_exists(self):
        """
        The _upsert_pending_followup method returns None when a pending record exists,
        preventing duplicate creation.
        """
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)
        old_email = _make_email_orm(received_at=now - timedelta(days=5))

        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = _make_pref_row(threshold=3)

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [old_email]

        # Existing pending followup found
        existing_followup = MagicMock(spec=FollowupORM)
        existing_followup.id = uuid.uuid4()
        existing_followup.status = "pending"

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_followup

        session.execute.side_effect = [pref_result, emails_result, existing_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        # No new followup should be created
        session.add.assert_not_called()
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_multiple_emails_each_get_one_followup(self):
        """
        Multiple qualifying emails each get exactly one pending followup record.
        """
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        email1 = _make_email_orm(received_at=now - timedelta(days=5))
        email2 = _make_email_orm(received_at=now - timedelta(days=7))

        inserted_followups: list[FollowupORM] = []

        def mock_add(obj):
            if isinstance(obj, FollowupORM):
                inserted_followups.append(obj)

        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock(side_effect=mock_add)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = _make_pref_row(threshold=3)

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [email1, email2]

        no_existing1 = MagicMock()
        no_existing1.scalar_one_or_none.return_value = None

        no_existing2 = MagicMock()
        no_existing2.scalar_one_or_none.return_value = None

        session.execute.side_effect = [pref_result, emails_result, no_existing1, no_existing2]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        assert len(suggestions) == 2
        assert len(inserted_followups) == 2
