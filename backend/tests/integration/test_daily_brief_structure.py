"""
Integration test: daily brief structure validation using hypothesis.

generate_daily_brief always returns exactly 3 urgent items, 2 followups, 1 non-empty risk string.
Tests with varied BriefContext inputs. Mocks DecisionEngine to return structured responses.

Requirements: 8.1
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from schemas.pydantic_schemas import (
    AnalyticsStats,
    BriefContext,
    CalendarEvent,
    DailyBrief,
    EmailMessage,
    FollowupSuggestion,
)
from services.decision_engine import DecisionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email(classification: str = "urgent") -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        gmail_id=f"gmail-{uuid.uuid4()}",
        thread_id=f"thread-{uuid.uuid4()}",
        subject="Test email",
        sender="sender@example.com",
        recipient="me@example.com",
        body_text="Test email body",
        received_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        classification=classification,
    )


def _make_followup() -> FollowupSuggestion:
    return FollowupSuggestion(
        id=uuid.uuid4(),
        email_id=uuid.uuid4(),
        sender="boss@example.com",
        subject="Follow up needed",
        sent_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        days_elapsed=5,
        draft_text="Following up...",
        status="pending",
    )


def _make_calendar_event() -> CalendarEvent:
    return CalendarEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Team Meeting",
        start_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
    )


def _make_analytics() -> AnalyticsStats:
    return AnalyticsStats(
        actions_automated=5,
        time_saved_minutes=25.0,
        emails_classified=10,
        replies_sent=3,
        events_created=2,
    )


def _make_engine_with_response(
    urgent_items: list[str],
    followups: list[str],
    risk: str,
) -> DecisionEngine:
    """Create a DecisionEngine mock that returns the given brief structure."""
    mock_openai = AsyncMock()
    mock_session = AsyncMock()

    response_json = json.dumps({
        "urgent_items": urgent_items,
        "followups": followups,
        "risk": risk,
    })

    choice = MagicMock()
    choice.message.content = response_json
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_openai.chat.completions.create.return_value = response

    return DecisionEngine(openai_client=mock_openai, session=mock_session)


# ---------------------------------------------------------------------------
# Hypothesis strategies for BriefContext
# ---------------------------------------------------------------------------


@st.composite
def brief_context_strategy(draw) -> BriefContext:
    """Generate varied BriefContext inputs."""
    num_urgent = draw(st.integers(min_value=0, max_value=5))
    num_followups = draw(st.integers(min_value=0, max_value=5))
    num_events = draw(st.integers(min_value=0, max_value=3))

    urgent_emails = [_make_email("urgent") for _ in range(num_urgent)]
    followups = [_make_followup() for _ in range(num_followups)]
    events = [_make_calendar_event() for _ in range(num_events)]

    return BriefContext(
        urgent_emails=urgent_emails,
        pending_followups=followups,
        upcoming_events=events,
        analytics_stats=_make_analytics(),
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestDailyBriefStructure:
    """Tests that generate_daily_brief always returns the correct structure."""

    @pytest.mark.asyncio
    async def test_brief_has_exactly_3_urgent_items(self):
        """generate_daily_brief returns exactly 3 urgent items."""
        engine = _make_engine_with_response(
            urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
            followups=["Followup 1", "Followup 2"],
            risk="Some risk",
        )

        context = BriefContext(
            urgent_emails=[_make_email("urgent")],
            pending_followups=[_make_followup()],
            upcoming_events=[_make_calendar_event()],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert len(brief.urgent_items) == 3

    @pytest.mark.asyncio
    async def test_brief_has_exactly_2_followups(self):
        """generate_daily_brief returns exactly 2 followups."""
        engine = _make_engine_with_response(
            urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
            followups=["Followup 1", "Followup 2"],
            risk="Some risk",
        )

        context = BriefContext(
            urgent_emails=[_make_email("urgent")],
            pending_followups=[_make_followup()],
            upcoming_events=[],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert len(brief.followups) == 2

    @pytest.mark.asyncio
    async def test_brief_has_non_empty_risk(self):
        """generate_daily_brief returns a non-empty risk string."""
        engine = _make_engine_with_response(
            urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
            followups=["Followup 1", "Followup 2"],
            risk="Deadline approaching for project X",
        )

        context = BriefContext(
            urgent_emails=[],
            pending_followups=[],
            upcoming_events=[],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert brief.risk != ""
        assert len(brief.risk) > 0

    @pytest.mark.asyncio
    async def test_brief_pads_urgent_items_when_llm_returns_fewer(self):
        """generate_daily_brief pads urgent_items to 3 when LLM returns fewer."""
        engine = _make_engine_with_response(
            urgent_items=["Only one"],
            followups=["Followup 1", "Followup 2"],
            risk="Some risk",
        )

        context = BriefContext(
            urgent_emails=[_make_email("urgent")],
            pending_followups=[_make_followup()],
            upcoming_events=[],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert len(brief.urgent_items) == 3

    @pytest.mark.asyncio
    async def test_brief_pads_followups_when_llm_returns_fewer(self):
        """generate_daily_brief pads followups to 2 when LLM returns fewer."""
        engine = _make_engine_with_response(
            urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
            followups=[],
            risk="Some risk",
        )

        context = BriefContext(
            urgent_emails=[],
            pending_followups=[],
            upcoming_events=[],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert len(brief.followups) == 2

    @pytest.mark.asyncio
    async def test_brief_uses_default_risk_when_empty(self):
        """generate_daily_brief uses default risk when LLM returns empty string."""
        engine = _make_engine_with_response(
            urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
            followups=["Followup 1", "Followup 2"],
            risk="",
        )

        context = BriefContext(
            urgent_emails=[],
            pending_followups=[],
            upcoming_events=[],
            analytics_stats=_make_analytics(),
        )

        brief = await engine.generate_daily_brief(context)

        assert brief.risk != ""


# ---------------------------------------------------------------------------
# Property-based test with hypothesis
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(context=brief_context_strategy())
def test_daily_brief_structure_invariant(context: BriefContext) -> None:
    """
    Property: generate_daily_brief always returns exactly 3 urgent items,
    2 followups, and 1 non-empty risk string, regardless of input context.

    Requirements: 8.1
    """
    import asyncio

    engine = _make_engine_with_response(
        urgent_items=["Urgent 1", "Urgent 2", "Urgent 3"],
        followups=["Followup 1", "Followup 2"],
        risk="Risk description",
    )

    brief = asyncio.run(engine.generate_daily_brief(context))

    assert len(brief.urgent_items) == 3, f"Expected 3 urgent items, got {len(brief.urgent_items)}"
    assert len(brief.followups) == 2, f"Expected 2 followups, got {len(brief.followups)}"
    assert brief.risk != "", "Risk string must not be empty"
    assert isinstance(brief.generated_at, datetime), "generated_at must be a datetime"
