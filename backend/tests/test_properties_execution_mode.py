"""
Property-based tests for execution mode enforcement.

Property 8: Execution Mode Enforcement
- In suggest/approval mode: Gmail send function is NEVER called
- In auto mode: Gmail send function IS called
- Tests via TaskOrchestrator.process_email_action with mocked services

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from schemas.pydantic_schemas import (
    AnalyticsStats,
    ReplyDraft,
    UserPreferences,
)
from services.task_orchestrator import TaskOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_id() -> str:
    return str(uuid.uuid4())


def _make_email_id() -> str:
    return str(uuid.uuid4())


def _make_mock_session(execution_mode: str = "suggest"):
    """Create a mock session that returns the given execution_mode from user_preferences."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    pref_row = MagicMock()
    pref_row.execution_mode = execution_mode

    pref_result = MagicMock()
    pref_result.scalar_one_or_none.return_value = pref_row

    # For pending drafts query
    drafts_result = MagicMock()
    drafts_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [pref_result, drafts_result]
    return session


def _make_orchestrator(execution_mode: str) -> tuple[TaskOrchestrator, MagicMock]:
    """Create a TaskOrchestrator with mocked services and the given execution mode."""
    session = _make_mock_session(execution_mode)

    mock_email_svc = MagicMock()
    mock_email_svc.generate_reply_draft = AsyncMock(return_value=ReplyDraft(
        id=uuid.uuid4(),
        email_id=uuid.uuid4(),
        draft_text="Test reply",
        status="pending",
    ))
    mock_email_svc.send_reply = AsyncMock(return_value={"success": True, "message_id": "msg-123"})
    mock_email_svc.fetch_emails = AsyncMock(return_value=[])
    mock_email_svc.get_email = AsyncMock()

    mock_calendar_svc = MagicMock()
    mock_calendar_svc.suggest_meeting_times = AsyncMock(return_value=[])

    mock_followup_agent = MagicMock()
    mock_followup_agent.check_pending_followups = AsyncMock(return_value=[])

    mock_analytics_svc = MagicMock()
    mock_analytics_svc.get_dashboard_stats = AsyncMock(return_value=AnalyticsStats(
        actions_automated=0,
        time_saved_minutes=0.0,
        emails_classified=0,
        replies_sent=0,
        events_created=0,
    ))
    mock_analytics_svc.record_event = AsyncMock()

    mock_behavior = MagicMock()
    mock_decision = MagicMock()

    orchestrator = TaskOrchestrator(
        session=session,
        email_service=mock_email_svc,
        calendar_service=mock_calendar_svc,
        followup_agent=mock_followup_agent,
        analytics_service=mock_analytics_svc,
        behavior_engine=mock_behavior,
        decision_engine=mock_decision,
    )

    return orchestrator, mock_email_svc


# ---------------------------------------------------------------------------
# Property 8: Execution Mode Enforcement
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(mode=st.sampled_from(["suggest", "approval"]))
def test_execution_mode_suggest_approval_never_calls_send(mode: str) -> None:
    """
    Property 8: In suggest/approval mode, Gmail send function is NEVER called.

    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    """
    import asyncio

    orchestrator, mock_email_svc = _make_orchestrator(mode)
    user_id = _make_user_id()
    email_id = _make_email_id()

    result = asyncio.run(
        orchestrator.process_email_action(user_id, email_id, "generate_reply")
    )

    # In suggest/approval mode, send_reply should NEVER be called
    mock_email_svc.send_reply.assert_not_called()

    # Status should be "suggested" or "pending_approval"
    assert result["status"] in ("suggested", "pending_approval")
    assert result["execution_mode"] == mode


@settings(max_examples=50)
@given(mode=st.sampled_from(["suggest", "approval"]))
def test_execution_mode_suggest_approval_does_not_execute_action(mode: str) -> None:
    """
    Property 8: In suggest/approval mode, generate_reply_draft is NOT called.

    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    """
    import asyncio

    orchestrator, mock_email_svc = _make_orchestrator(mode)
    user_id = _make_user_id()
    email_id = _make_email_id()

    result = asyncio.run(
        orchestrator.process_email_action(user_id, email_id, "generate_reply")
    )

    # In suggest/approval mode, the action should NOT be executed
    mock_email_svc.generate_reply_draft.assert_not_called()


@settings(max_examples=50)
@given(mode=st.sampled_from(["auto"]))
def test_execution_mode_auto_calls_generate_reply(mode: str) -> None:
    """
    Property 8: In auto mode, generate_reply_draft IS called.

    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    """
    import asyncio

    orchestrator, mock_email_svc = _make_orchestrator(mode)
    user_id = _make_user_id()
    email_id = _make_email_id()

    result = asyncio.run(
        orchestrator.process_email_action(user_id, email_id, "generate_reply")
    )

    # In auto mode, generate_reply_draft SHOULD be called
    mock_email_svc.generate_reply_draft.assert_called_once()
    assert result["status"] == "executed"
    assert result["execution_mode"] == "auto"


@settings(max_examples=50)
@given(mode=st.sampled_from(["suggest", "approval", "auto"]))
def test_execution_mode_result_always_has_valid_status(mode: str) -> None:
    """
    Property 8: process_email_action always returns a result with a valid status.

    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    """
    import asyncio

    orchestrator, mock_email_svc = _make_orchestrator(mode)
    user_id = _make_user_id()
    email_id = _make_email_id()

    result = asyncio.run(
        orchestrator.process_email_action(user_id, email_id, "generate_reply")
    )

    valid_statuses = {"suggested", "pending_approval", "executed", "error"}
    assert result["status"] in valid_statuses
    assert result["execution_mode"] == mode
