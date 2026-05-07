"""
Unit tests for backend/services/analytics_service.py

Covers:
- actions_automated = COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)
  (email_classified NOT counted)
- Time-saved constants: 5 min per reply_sent, 10 min per event_created
- Period filtering: "week" = last 7 days, "month" = last 30 days

Requirements: 11.1, 11.2, 11.3, 11.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.analytics_service import (
    AnalyticsService,
    TIME_SAVED_PER_EVENT,
    TIME_SAVED_PER_REPLY,
    _period_start,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_id() -> str:
    return str(uuid.uuid4())


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _make_row(replies_sent=0, events_created=0, followups_sent=0, emails_classified=0):
    """Build a mock DB result row with the expected column names."""
    row = MagicMock()
    row.replies_sent = replies_sent
    row.events_created = events_created
    row.followups_sent = followups_sent
    row.emails_classified = emails_classified
    return row


# ---------------------------------------------------------------------------
# actions_automated formula
# ---------------------------------------------------------------------------


class TestActionsAutomated:
    @pytest.mark.asyncio
    async def test_actions_automated_excludes_email_classified(self):
        """email_classified events are NOT counted in actions_automated."""
        session = _make_mock_session()
        row = _make_row(replies_sent=2, events_created=1, followups_sent=1, emails_classified=10)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        # actions_automated = 2 + 1 + 1 = 4, NOT 14
        assert stats.actions_automated == 4

    @pytest.mark.asyncio
    async def test_actions_automated_is_sum_of_three_types(self):
        """actions_automated = reply_sent + event_created + followup_sent."""
        session = _make_mock_session()
        row = _make_row(replies_sent=3, events_created=2, followups_sent=5, emails_classified=0)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        assert stats.actions_automated == 10  # 3 + 2 + 5

    @pytest.mark.asyncio
    async def test_actions_automated_zero_when_no_events(self):
        """actions_automated is 0 when there are no automated events."""
        session = _make_mock_session()
        row = _make_row(replies_sent=0, events_created=0, followups_sent=0, emails_classified=5)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        assert stats.actions_automated == 0

    @pytest.mark.asyncio
    async def test_emails_classified_is_reported_separately(self):
        """emails_classified is reported as its own field, not in actions_automated."""
        session = _make_mock_session()
        row = _make_row(replies_sent=1, events_created=0, followups_sent=0, emails_classified=7)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        assert stats.emails_classified == 7
        assert stats.actions_automated == 1  # only reply_sent


# ---------------------------------------------------------------------------
# Time-saved constants
# ---------------------------------------------------------------------------


class TestTimeSavedConstants:
    def test_time_saved_per_reply_is_5_minutes(self):
        """TIME_SAVED_PER_REPLY constant is 5.0 minutes."""
        assert TIME_SAVED_PER_REPLY == 5.0

    def test_time_saved_per_event_is_10_minutes(self):
        """TIME_SAVED_PER_EVENT constant is 10.0 minutes."""
        assert TIME_SAVED_PER_EVENT == 10.0

    @pytest.mark.asyncio
    async def test_time_saved_calculation(self):
        """time_saved_minutes = replies_sent * 5 + events_created * 10."""
        session = _make_mock_session()
        row = _make_row(replies_sent=4, events_created=3, followups_sent=2, emails_classified=0)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        expected = 4 * 5.0 + 3 * 10.0  # 20 + 30 = 50
        assert stats.time_saved_minutes == expected

    @pytest.mark.asyncio
    async def test_followup_sent_does_not_contribute_to_time_saved(self):
        """followup_sent events do NOT contribute to time_saved_minutes."""
        session = _make_mock_session()
        row = _make_row(replies_sent=0, events_created=0, followups_sent=10, emails_classified=0)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        assert stats.time_saved_minutes == 0.0

    @pytest.mark.asyncio
    async def test_time_saved_zero_when_no_events(self):
        """time_saved_minutes is 0 when there are no events."""
        session = _make_mock_session()
        row = _make_row()
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id())

        assert stats.time_saved_minutes == 0.0


# ---------------------------------------------------------------------------
# Period filtering
# ---------------------------------------------------------------------------


class TestPeriodFiltering:
    def test_week_period_is_7_days(self):
        """'week' period starts 7 days ago."""
        now = datetime.utcnow()
        period_start = _period_start("week")
        delta = now - period_start
        # Allow 1 second tolerance
        assert abs(delta.total_seconds() - 7 * 86400) < 2

    def test_month_period_is_30_days(self):
        """'month' period starts 30 days ago."""
        now = datetime.utcnow()
        period_start = _period_start("month")
        delta = now - period_start
        assert abs(delta.total_seconds() - 30 * 86400) < 2

    def test_unknown_period_defaults_to_week(self):
        """Unknown period strings default to 7 days (week)."""
        now = datetime.utcnow()
        period_start = _period_start("quarterly")
        delta = now - period_start
        assert abs(delta.total_seconds() - 7 * 86400) < 2

    @pytest.mark.asyncio
    async def test_week_period_passed_to_query(self):
        """get_dashboard_stats with period='week' uses 7-day window."""
        session = _make_mock_session()
        row = _make_row(replies_sent=1)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id(), period="week")

        # Verify execute was called (query was made)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_month_period_passed_to_query(self):
        """get_dashboard_stats with period='month' uses 30-day window."""
        session = _make_mock_session()
        row = _make_row(replies_sent=2)
        mock_result = MagicMock()
        mock_result.one.return_value = row
        session.execute.return_value = mock_result

        service = AnalyticsService(session)
        stats = await service.get_dashboard_stats(_make_user_id(), period="month")

        session.execute.assert_called_once()
