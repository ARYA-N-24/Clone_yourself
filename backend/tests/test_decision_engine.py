"""
Unit tests for backend/services/decision_engine.py

Covers:
- classify_email: urgent/normal/low paths, default-to-normal on exhausted retries
- generate_reply: tone injection (formal/casual), empty similar-emails fallback
- suggest_meeting_slots: top-3 limit enforced
- generate_daily_brief: structure validation (3 urgent, 2 followups, 1 risk)
- Exponential backoff retry: verify sleep(2), sleep(4), sleep(8) called on RateLimitError

Requirements: 3.1, 3.2, 3.5, 3.6, 4.1, 4.7, 4.8, 6.6, 8.1
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import openai
import pytest

from backend.schemas.pydantic_schemas import (
    AnalyticsStats,
    BriefContext,
    CalendarEvent,
    EmailMessage,
    FollowupSuggestion,
    StyleContext,
    TimeSlot,
    UserPreferences,
)
from backend.services.decision_engine import DecisionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email(
    classification=None,
    subject="Test Subject",
    sender="sender@example.com",
    body_text="Hello, please reply to this email.",
) -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        gmail_id="gmail-123",
        thread_id="thread-123",
        subject=subject,
        sender=sender,
        recipient="me@example.com",
        body_text=body_text,
        received_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        classification=classification,
    )


def _make_user_prefs(tone="casual") -> UserPreferences:
    return UserPreferences(tone=tone)


def _make_engine() -> tuple[DecisionEngine, AsyncMock]:
    """Return (engine, mock_openai_client)."""
    mock_openai = AsyncMock()
    mock_session = AsyncMock()
    engine = DecisionEngine(openai_client=mock_openai, session=mock_session)
    return engine, mock_openai


def _make_chat_response(content: str) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    return response


# ---------------------------------------------------------------------------
# classify_email
# ---------------------------------------------------------------------------


class TestClassifyEmail:
    @pytest.mark.asyncio
    async def test_classify_urgent(self):
        """Returns 'urgent' when OpenAI returns classification=urgent."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({"classification": "urgent", "category": "action-required"})
        )

        result = await engine.classify_email(_make_email(), _make_user_prefs())
        assert result == "urgent"

    @pytest.mark.asyncio
    async def test_classify_normal(self):
        """Returns 'normal' when OpenAI returns classification=normal."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({"classification": "normal", "category": "info"})
        )

        result = await engine.classify_email(_make_email(), _make_user_prefs())
        assert result == "normal"

    @pytest.mark.asyncio
    async def test_classify_low(self):
        """Returns 'low' when OpenAI returns classification=low."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({"classification": "low", "category": "info"})
        )

        result = await engine.classify_email(_make_email(), _make_user_prefs())
        assert result == "low"

    @pytest.mark.asyncio
    async def test_default_to_normal_on_exhausted_retries(self):
        """Returns 'normal' when all retries are exhausted with RateLimitError."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
            message="rate limit", response=MagicMock(), body={}
        )

        with patch("backend.services.decision_engine.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await engine.classify_email(_make_email(), _make_user_prefs())

        assert result == "normal"

    @pytest.mark.asyncio
    async def test_default_to_normal_on_invalid_json(self):
        """Returns 'normal' when OpenAI returns invalid JSON."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "not valid json"
        )

        result = await engine.classify_email(_make_email(), _make_user_prefs())
        assert result == "normal"

    @pytest.mark.asyncio
    async def test_default_to_normal_on_unknown_label(self):
        """Returns 'normal' when OpenAI returns an unrecognised classification."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({"classification": "critical", "category": "other"})
        )

        result = await engine.classify_email(_make_email(), _make_user_prefs())
        assert result == "normal"


# ---------------------------------------------------------------------------
# generate_reply
# ---------------------------------------------------------------------------


class TestGenerateReply:
    @pytest.mark.asyncio
    async def test_formal_tone_injected(self):
        """Formal tone is injected into the system prompt."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "Dear Sir, thank you for your email."
        )

        style_ctx = StyleContext(tone="formal", similar_emails=[])
        draft = await engine.generate_reply(_make_email(), style_ctx)

        # Verify the system prompt contains "formal"
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "formal" in system_msg

    @pytest.mark.asyncio
    async def test_casual_tone_injected(self):
        """Casual tone is injected into the system prompt."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "Hey, thanks for reaching out!"
        )

        style_ctx = StyleContext(tone="casual", similar_emails=[])
        draft = await engine.generate_reply(_make_email(), style_ctx)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "casual" in system_msg

    @pytest.mark.asyncio
    async def test_empty_similar_emails_fallback(self):
        """When similar_emails is empty, uses '(no examples available)' fallback."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "Sure, I'll get back to you."
        )

        style_ctx = StyleContext(tone="casual", similar_emails=[])
        draft = await engine.generate_reply(_make_email(), style_ctx)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "(no examples available)" in system_msg

    @pytest.mark.asyncio
    async def test_similar_emails_included_in_prompt(self):
        """When similar_emails are provided, they appear in the system prompt."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "Thanks for your message."
        )

        similar = _make_email(body_text="Example past email body here.")
        style_ctx = StyleContext(tone="casual", similar_emails=[similar])
        await engine.generate_reply(_make_email(), style_ctx)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "Example past email body here." in system_msg

    @pytest.mark.asyncio
    async def test_returns_reply_draft_with_pending_status(self):
        """generate_reply always returns a ReplyDraft with status='pending'."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "Here is my reply."
        )

        style_ctx = StyleContext(tone="casual", similar_emails=[])
        draft = await engine.generate_reply(_make_email(), style_ctx)

        assert draft.status == "pending"
        assert draft.draft_text == "Here is my reply."


# ---------------------------------------------------------------------------
# suggest_meeting_slots
# ---------------------------------------------------------------------------


class TestSuggestMeetingSlots:
    def _make_slots(self, n: int) -> list[TimeSlot]:
        slots = []
        for i in range(n):
            start = datetime(2024, 1, 15, 9 + i, 0, tzinfo=timezone.utc)
            end = datetime(2024, 1, 15, 9 + i, 30, tzinfo=timezone.utc)
            slots.append(TimeSlot(start=start, end=end))
        return slots

    def _make_llm_slots_response(self, n: int) -> str:
        items = []
        for i in range(n):
            items.append({
                "slot": {
                    "start": f"2024-01-15T{9+i:02d}:00:00",
                    "end": f"2024-01-15T{9+i:02d}:30:00",
                },
                "confidence_score": 0.9 - i * 0.1,
                "reason": f"Slot {i+1} reason",
            })
        return json.dumps(items)

    @pytest.mark.asyncio
    async def test_top_3_limit_enforced_when_llm_returns_more(self):
        """Returns at most 3 slots even when LLM returns more."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            self._make_llm_slots_response(5)
        )

        slots = self._make_slots(5)
        result = await engine.suggest_meeting_slots(_make_email(), slots)

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_returns_empty_on_openai_error(self):
        """Returns empty list when OpenAI raises an error."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.side_effect = openai.OpenAIError("error")

        result = await engine.suggest_meeting_slots(_make_email(), self._make_slots(3))
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self):
        """Returns empty list when LLM returns invalid JSON."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "not json"
        )

        result = await engine.suggest_meeting_slots(_make_email(), self._make_slots(3))
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_up_to_3_valid_slots(self):
        """Returns exactly 3 slots when LLM returns exactly 3."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            self._make_llm_slots_response(3)
        )

        result = await engine.suggest_meeting_slots(_make_email(), self._make_slots(3))
        assert len(result) == 3


# ---------------------------------------------------------------------------
# generate_daily_brief
# ---------------------------------------------------------------------------


class TestGenerateDailyBrief:
    def _make_brief_context(self) -> BriefContext:
        urgent_email = _make_email(classification="urgent")
        followup = FollowupSuggestion(
            id=uuid.uuid4(),
            email_id=uuid.uuid4(),
            sender="boss@example.com",
            subject="Follow up",
            sent_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
            days_elapsed=5,
            draft_text="Following up...",
            status="pending",
        )
        event = CalendarEvent(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="Team Meeting",
            start_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
        )
        stats = AnalyticsStats(
            actions_automated=5,
            time_saved_minutes=25.0,
            emails_classified=10,
            replies_sent=3,
            events_created=2,
        )
        return BriefContext(
            urgent_emails=[urgent_email],
            pending_followups=[followup],
            upcoming_events=[event],
            analytics_stats=stats,
        )

    @pytest.mark.asyncio
    async def test_returns_exactly_3_urgent_items(self):
        """generate_daily_brief always returns exactly 3 urgent items."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Item 1", "Item 2", "Item 3"],
                "followups": ["Followup 1", "Followup 2"],
                "risk": "Some risk here",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert len(brief.urgent_items) == 3

    @pytest.mark.asyncio
    async def test_returns_exactly_2_followups(self):
        """generate_daily_brief always returns exactly 2 followups."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Item 1", "Item 2", "Item 3"],
                "followups": ["Followup 1", "Followup 2"],
                "risk": "Some risk here",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert len(brief.followups) == 2

    @pytest.mark.asyncio
    async def test_returns_non_empty_risk(self):
        """generate_daily_brief always returns a non-empty risk string."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Item 1", "Item 2", "Item 3"],
                "followups": ["Followup 1", "Followup 2"],
                "risk": "Deadline approaching",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert brief.risk != ""

    @pytest.mark.asyncio
    async def test_pads_urgent_items_when_llm_returns_fewer(self):
        """Pads urgent_items to 3 when LLM returns fewer."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Only one item"],
                "followups": ["Followup 1", "Followup 2"],
                "risk": "Some risk",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert len(brief.urgent_items) == 3

    @pytest.mark.asyncio
    async def test_pads_followups_when_llm_returns_fewer(self):
        """Pads followups to 2 when LLM returns fewer."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Item 1", "Item 2", "Item 3"],
                "followups": [],
                "risk": "Some risk",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert len(brief.followups) == 2

    @pytest.mark.asyncio
    async def test_uses_default_risk_when_empty(self):
        """Uses default risk string when LLM returns empty risk."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            json.dumps({
                "urgent_items": ["Item 1", "Item 2", "Item 3"],
                "followups": ["Followup 1", "Followup 2"],
                "risk": "",
            })
        )

        brief = await engine.generate_daily_brief(self._make_brief_context())
        assert brief.risk != ""


# ---------------------------------------------------------------------------
# Exponential backoff retry
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    @pytest.mark.asyncio
    async def test_sleep_called_with_2_4_8_on_rate_limit_errors(self):
        """Verifies sleep(2), sleep(4), sleep(8) are called on consecutive RateLimitErrors."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
            message="rate limit", response=MagicMock(), body={}
        )

        with patch("backend.services.decision_engine.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await engine.classify_email(_make_email(), _make_user_prefs())

        # Should have slept 3 times: 2, 4, 8
        assert mock_sleep.call_count == 3
        mock_sleep.assert_has_calls([call(2), call(4), call(8)])

    @pytest.mark.asyncio
    async def test_returns_normal_after_all_retries_exhausted(self):
        """Returns 'normal' after all 3 retries are exhausted."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
            message="rate limit", response=MagicMock(), body={}
        )

        with patch("backend.services.decision_engine.asyncio.sleep", new_callable=AsyncMock):
            result = await engine.classify_email(_make_email(), _make_user_prefs())

        assert result == "normal"

    @pytest.mark.asyncio
    async def test_succeeds_on_second_attempt(self):
        """Succeeds on second attempt after one RateLimitError."""
        engine, mock_openai = _make_engine()
        mock_openai.chat.completions.create.side_effect = [
            openai.RateLimitError(message="rate limit", response=MagicMock(), body={}),
            _make_chat_response(json.dumps({"classification": "urgent", "category": "action-required"})),
        ]

        with patch("backend.services.decision_engine.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await engine.classify_email(_make_email(), _make_user_prefs())

        assert result == "urgent"
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_once_with(2)
