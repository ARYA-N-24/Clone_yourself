"""
Property-based tests for email classification.

Property 1: Classification Completeness
- For any email text, the result must always be in {"urgent", "normal", "low"}
- Mock OpenAI to return each label deterministically
- Also test default-on-failure path

**Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.schemas.pydantic_schemas import EmailMessage, UserPreferences
from backend.services.decision_engine import DecisionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> tuple[DecisionEngine, AsyncMock]:
    mock_openai = AsyncMock()
    mock_session = AsyncMock()
    engine = DecisionEngine(openai_client=mock_openai, session=mock_session)
    return engine, mock_openai


def _make_chat_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return response


def _make_email_from_text(body_text: str) -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        gmail_id="gmail-prop-test",
        thread_id="thread-prop-test",
        subject="Property test subject",
        sender="sender@example.com",
        recipient="me@example.com",
        body_text=body_text,
        received_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
    )


VALID_LABELS = {"urgent", "normal", "low"}


# ---------------------------------------------------------------------------
# Property 1: Classification Completeness — deterministic label paths
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_urgent_label(body_text: str) -> None:
    """
    Property 1: When OpenAI returns 'urgent', result is always 'urgent'.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.return_value = _make_chat_response(
        json.dumps({"classification": "urgent", "category": "action-required"})
    )

    import asyncio
    result = asyncio.run(
        engine.classify_email(
            _make_email_from_text(body_text),
            UserPreferences(),
        )
    )

    assert result in VALID_LABELS
    assert result == "urgent"


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_normal_label(body_text: str) -> None:
    """
    Property 1: When OpenAI returns 'normal', result is always 'normal'.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.return_value = _make_chat_response(
        json.dumps({"classification": "normal", "category": "info"})
    )

    import asyncio
    result = asyncio.run(
        engine.classify_email(
            _make_email_from_text(body_text),
            UserPreferences(),
        )
    )

    assert result in VALID_LABELS
    assert result == "normal"


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_low_label(body_text: str) -> None:
    """
    Property 1: When OpenAI returns 'low', result is always 'low'.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.return_value = _make_chat_response(
        json.dumps({"classification": "low", "category": "info"})
    )

    import asyncio
    result = asyncio.run(
        engine.classify_email(
            _make_email_from_text(body_text),
            UserPreferences(),
        )
    )

    assert result in VALID_LABELS
    assert result == "low"


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_default_on_failure(body_text: str) -> None:
    """
    Property 1: When OpenAI fails (RateLimitError), result is always in valid set.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
        message="rate limit", response=MagicMock(), body={}
    )

    import asyncio
    with patch("backend.services.decision_engine.asyncio.sleep", new_callable=AsyncMock):
        result = asyncio.run(
            engine.classify_email(
                _make_email_from_text(body_text),
                UserPreferences(),
            )
        )

    assert result in VALID_LABELS


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_default_on_invalid_json(body_text: str) -> None:
    """
    Property 1: When OpenAI returns invalid JSON, result is always in valid set.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.return_value = _make_chat_response(
        "this is not valid json at all"
    )

    import asyncio
    result = asyncio.run(
        engine.classify_email(
            _make_email_from_text(body_text),
            UserPreferences(),
        )
    )

    assert result in VALID_LABELS


@settings(max_examples=50)
@given(body_text=st.text(min_size=10, max_size=500))
def test_classification_completeness_unknown_label_defaults_to_normal(body_text: str) -> None:
    """
    Property 1: When OpenAI returns an unknown label, result defaults to 'normal'.

    **Validates: Requirements 3.1, 3.2, 3.5, 3.6, 4.1**
    """
    engine, mock_openai = _make_engine()
    mock_openai.chat.completions.create.return_value = _make_chat_response(
        json.dumps({"classification": "critical", "category": "other"})
    )

    import asyncio
    result = asyncio.run(
        engine.classify_email(
            _make_email_from_text(body_text),
            UserPreferences(),
        )
    )

    assert result in VALID_LABELS
    assert result == "normal"
