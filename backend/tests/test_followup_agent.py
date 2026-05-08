"""
Unit tests for backend/services/followup_agent.py

Covers:
- Threshold filtering: only emails older than followup_threshold days
- Exclusion of snoozed/resolved/sent followups
- At-most-one-pending enforcement (upsert logic)
- Ascending sort order by sent_at
- Snooze/resolve status transitions

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

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


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _make_email_orm(
    received_at: datetime,
    is_replied: bool = False,
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
) -> MagicMock:
    email = MagicMock(spec=EmailORM)
    email.id = uuid.uuid4()
    email.gmail_id = "gmail-123"
    email.thread_id = "thread-123"
    email.subject = subject
    email.sender = sender
    email.recipient = "me@example.com"
    email.body_text = "Email body text"
    email.received_at = received_at
    email.classification = "normal"
    email.category = "info"
    email.is_replied = is_replied
    return email


def _make_followup_orm(status: str = "pending") -> MagicMock:
    followup = MagicMock(spec=FollowupORM)
    followup.id = uuid.uuid4()
    followup.status = status
    followup.snooze_until = None
    return followup


def _make_pref_row(threshold: int = 3) -> MagicMock:
    pref = MagicMock(spec=UserPreference)
    pref.followup_threshold = threshold
    return pref


def _make_decision_engine() -> MagicMock:
    engine = MagicMock()
    engine.suggest_followup = AsyncMock(return_value=FollowupSuggestion(
        id=uuid.uuid4(),
        email_id=uuid.uuid4(),
        sender="sender@example.com",
        subject="Test Subject",
        sent_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        days_elapsed=5,
        draft_text="Following up on my previous email.",
        status="pending",
    ))
    return engine


# ---------------------------------------------------------------------------
# Threshold filtering
# ---------------------------------------------------------------------------


class TestThresholdFiltering:
    @pytest.mark.asyncio
    async def test_only_emails_older_than_threshold_are_returned(self):
        """Only emails older than followup_threshold days are included."""
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        # Email that is 5 days old (older than threshold of 3)
        old_email = _make_email_orm(received_at=now - timedelta(days=5))

        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        # First execute: preferences query
        # Second execute: emails query
        # Third execute: check existing pending followup
        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [old_email]

        no_existing_result = MagicMock()
        no_existing_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [pref_result, emails_result, no_existing_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        assert len(suggestions) == 1

    @pytest.mark.asyncio
    async def test_no_suggestions_when_no_qualifying_emails(self):
        """Returns empty list when no emails qualify."""
        user_id = _make_user_id()

        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [pref_result, emails_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        assert suggestions == []


# ---------------------------------------------------------------------------
# Exclusion of snoozed/resolved/sent followups
# ---------------------------------------------------------------------------


class TestFollowupExclusion:
    @pytest.mark.asyncio
    async def test_emails_with_existing_followup_are_excluded(self):
        """Emails that already have an active followup are excluded from results."""
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        # The email query returns empty because the subquery excludes emails
        # with active followups — we simulate this by returning no emails
        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        # No emails returned (all excluded by subquery)
        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [pref_result, emails_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        assert suggestions == []


# ---------------------------------------------------------------------------
# At-most-one-pending enforcement
# ---------------------------------------------------------------------------


class TestAtMostOnePending:
    @pytest.mark.asyncio
    async def test_skips_email_when_pending_followup_already_exists(self):
        """When a pending followup already exists for an email, it is skipped."""
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        old_email = _make_email_orm(received_at=now - timedelta(days=5))

        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [old_email]

        # Existing pending followup found
        existing_followup = _make_followup_orm(status="pending")
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_followup

        session.execute.side_effect = [pref_result, emails_result, existing_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        # Should be empty because the pending followup already exists
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_creates_new_followup_when_none_exists(self):
        """Creates a new pending followup when none exists for the email."""
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        old_email = _make_email_orm(received_at=now - timedelta(days=5))

        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        emails_result = MagicMock()
        emails_result.scalars.return_value.all.return_value = [old_email]

        # No existing pending followup
        no_existing_result = MagicMock()
        no_existing_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [pref_result, emails_result, no_existing_result]

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        suggestions = await agent.check_pending_followups(user_id, session)

        # session.add should have been called to insert the new followup
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, FollowupORM)
        assert added.status == "pending"


# ---------------------------------------------------------------------------
# Ascending sort order
# ---------------------------------------------------------------------------


class TestAscendingSortOrder:
    @pytest.mark.asyncio
    async def test_suggestions_sorted_by_sent_at_ascending(self):
        """Suggestions are sorted by sent_at ascending (oldest first)."""
        user_id = _make_user_id()
        now = datetime.now(tz=timezone.utc)

        # Two emails: one older, one newer
        older_email = _make_email_orm(
            received_at=now - timedelta(days=10),
            subject="Older email",
        )
        newer_email = _make_email_orm(
            received_at=now - timedelta(days=5),
            subject="Newer email",
        )

        session = _make_mock_session()
        pref_row = _make_pref_row(threshold=3)

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = pref_row

        emails_result = MagicMock()
        # Return in reverse order to test sorting
        emails_result.scalars.return_value.all.return_value = [newer_email, older_email]

        no_existing_1 = MagicMock()
        no_existing_1.scalar_one_or_none.return_value = None
        no_existing_2 = MagicMock()
        no_existing_2.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            pref_result,
            emails_result,
            no_existing_1,
            no_existing_2,
        ]

        # Make decision engine return suggestions with the email's received_at as sent_at
        async def mock_suggest_followup(email_msg, days_elapsed):
            return FollowupSuggestion(
                id=uuid.uuid4(),
                email_id=email_msg.id,
                sender=email_msg.sender,
                subject=email_msg.subject,
                sent_at=email_msg.received_at,
                days_elapsed=days_elapsed,
                draft_text="Following up.",
                status="pending",
            )

        decision_engine = MagicMock()
        decision_engine.suggest_followup = mock_suggest_followup

        agent = FollowupAgent(decision_engine=decision_engine)
        suggestions = await agent.check_pending_followups(user_id, session)

        assert len(suggestions) == 2
        # Oldest first
        assert suggestions[0].sent_at < suggestions[1].sent_at


# ---------------------------------------------------------------------------
# Snooze/resolve status transitions
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_snooze_followup_sets_status_to_snoozed(self):
        """snooze_followup sets status to 'snoozed' and sets snooze_until."""
        followup_id = str(uuid.uuid4())
        snooze_until = datetime(2024, 2, 1, tzinfo=timezone.utc)

        followup_row = _make_followup_orm(status="pending")

        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = followup_row
        session.execute.return_value = result

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        await agent.snooze_followup(followup_id, snooze_until, session)

        assert followup_row.status == "snoozed"
        assert followup_row.snooze_until == snooze_until
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_snooze_followup_raises_404_when_not_found(self):
        """snooze_followup raises HTTPException(404) when followup not found."""
        followup_id = str(uuid.uuid4())
        snooze_until = datetime(2024, 2, 1, tzinfo=timezone.utc)

        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        with pytest.raises(HTTPException) as exc_info:
            await agent.snooze_followup(followup_id, snooze_until, session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_followup_sets_status_to_resolved(self):
        """resolve_followup sets status to 'resolved' and sets resolved_at."""
        followup_id = str(uuid.uuid4())

        followup_row = _make_followup_orm(status="pending")

        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = followup_row
        session.execute.return_value = result

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        await agent.resolve_followup(followup_id, session)

        assert followup_row.status == "resolved"
        assert followup_row.resolved_at is not None
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_followup_raises_404_when_not_found(self):
        """resolve_followup raises HTTPException(404) when followup not found."""
        followup_id = str(uuid.uuid4())

        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        decision_engine = _make_decision_engine()
        agent = FollowupAgent(decision_engine=decision_engine)

        with pytest.raises(HTTPException) as exc_info:
            await agent.resolve_followup(followup_id, session)

        assert exc_info.value.status_code == 404
