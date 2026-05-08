"""
Task Orchestrator for the Clone Yourself Platform.

Central coordinator that routes incoming requests to the appropriate service,
manages execution mode (Suggest/Approval/Auto), and aggregates results for
the frontend.

Interface:
    - get_dashboard(user_id) → DashboardPayload
    - process_email_action(user_id, email_id, action) → ActionResult
    - run_followup_check(user_id) → list[FollowupSuggestion]
    - generate_daily_brief(user_id) → DailyBrief
    - get_execution_mode(user_id) → ExecutionMode

Requirements: 2.1, 2.2, 2.4, 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import ReplyDraft as ReplyDraftORM
from models.db_models import UserPreference
from schemas.pydantic_schemas import (
    AnalyticsEvent,
    AnalyticsStats,
    BriefContext,
    DailyBrief,
    DashboardPayload,
    EmailMessage,
    FollowupSuggestion,
    ReplyDraft,
)
from services.analytics_service import AnalyticsService
from services.behavior_engine import BehaviorEngine
from services.calendar_service import CalendarService
from services.decision_engine import DecisionEngine
from services.email_service import EmailService
from services.followup_agent import FollowupAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Execution mode is one of three string literals
ExecutionMode = Literal["suggest", "approval", "auto"]

# Action types the orchestrator can process
ActionType = Literal["generate_reply", "send_reply", "create_event", "send_followup"]


class ActionResult(TypedDict):
    """Result returned by process_email_action."""

    action: str
    status: Literal["suggested", "pending_approval", "executed", "error"]
    execution_mode: str
    data: Any
    message: str


# ---------------------------------------------------------------------------
# TaskOrchestrator
# ---------------------------------------------------------------------------


class TaskOrchestrator:
    """
    Central coordinator that routes requests to appropriate services,
    enforces execution mode, and aggregates results for the frontend.

    Args:
        session: SQLAlchemy AsyncSession for direct DB queries (e.g. pending drafts).
        email_service: EmailService for fetching and replying to emails.
        calendar_service: CalendarService for calendar operations.
        followup_agent: FollowupAgent for follow-up detection and management.
        analytics_service: AnalyticsService for stats and event recording.
        behavior_engine: BehaviorEngine for user preferences and style context.
        decision_engine: DecisionEngine for LLM-powered brief generation.
    """

    def __init__(
        self,
        session: AsyncSession,
        email_service: EmailService,
        calendar_service: CalendarService,
        followup_agent: FollowupAgent,
        analytics_service: AnalyticsService,
        behavior_engine: BehaviorEngine,
        decision_engine: DecisionEngine,
    ) -> None:
        self._session = session
        self._email_svc = email_service
        self._calendar_svc = calendar_service
        self._followup_agent = followup_agent
        self._analytics_svc = analytics_service
        self._behavior = behavior_engine
        self._decision = decision_engine

    # ------------------------------------------------------------------
    # get_execution_mode
    # ------------------------------------------------------------------

    async def get_execution_mode(self, user_id: str) -> ExecutionMode:
        """
        Return the user's current execution mode from user_preferences.

        Defaults to "suggest" if no preferences row exists.

        Args:
            user_id: UUID string of the user.

        Returns:
            One of "suggest", "approval", or "auto".

        Requirements: 10.1, 10.2, 10.3, 10.4
        """
        user_uuid = UUID(user_id)
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await self._session.execute(stmt)
        pref_row = result.scalar_one_or_none()

        if pref_row is None:
            logger.debug(
                "No preferences found for user %s; defaulting execution_mode to 'suggest'.",
                user_id,
            )
            return "suggest"

        mode = pref_row.execution_mode
        if mode not in ("suggest", "approval", "auto"):
            logger.warning(
                "Unexpected execution_mode %r for user %s; defaulting to 'suggest'.",
                mode,
                user_id,
            )
            return "suggest"

        return mode  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # get_dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(self, user_id: str) -> DashboardPayload:
        """
        Aggregate and return the full dashboard payload for the user.

        Fetches emails, analytics stats, and the daily brief concurrently
        using asyncio.gather() with return_exceptions=True (Requirement 2.4).
        If any individual service fails, its result is replaced with a safe
        default so the remaining data is still returned (Requirement 2.2).

        The payload contains:
        - priority_emails: urgent and normal emails (Requirement 2.1)
        - pending_replies: reply drafts with status="pending"
        - suggested_actions: human-readable action strings
        - followup_count: number of pending follow-ups
        - analytics: aggregated productivity stats

        Args:
            user_id: UUID string of the user.

        Returns:
            DashboardPayload with all available data.

        Requirements: 2.1, 2.2, 2.4
        """
        logger.info("Building dashboard for user %s.", user_id)

        # ----------------------------------------------------------------
        # Sequential fetch: emails, analytics stats, and daily brief
        # (Using sequential fetch to prevent asyncpg InterfaceError on shared session)
        # ----------------------------------------------------------------
        
        try:
            emails_result = await self._email_svc.fetch_emails(user_id)
        except Exception as e:
            emails_result = e
            
        try:
            analytics_result = await self._analytics_svc.get_dashboard_stats(user_id)
        except Exception as e:
            analytics_result = e
            
        try:
            followup_result = await self._followup_agent.check_pending_followups(user_id, self._session)
        except Exception as e:
            followup_result = e

        # ----------------------------------------------------------------
        # Handle partial failures gracefully (Requirement 2.2)
        # ----------------------------------------------------------------

        # Emails
        if isinstance(emails_result, Exception):
            logger.error(
                "Email service failed for user %s during dashboard load: %s",
                user_id,
                emails_result,
            )
            all_emails: list[EmailMessage] = []
        else:
            all_emails = emails_result  # type: ignore[assignment]

        # Analytics
        if isinstance(analytics_result, Exception):
            logger.error(
                "Analytics service failed for user %s during dashboard load: %s",
                user_id,
                analytics_result,
            )
            analytics_stats = AnalyticsStats(
                actions_automated=0,
                time_saved_minutes=0.0,
                emails_classified=0,
                replies_sent=0,
                events_created=0,
            )
        else:
            analytics_stats = analytics_result  # type: ignore[assignment]

        # Follow-ups
        if isinstance(followup_result, Exception):
            logger.error(
                "Followup agent failed for user %s during dashboard load: %s",
                user_id,
                followup_result,
            )
            followup_suggestions: list[FollowupSuggestion] = []
        else:
            followup_suggestions = followup_result  # type: ignore[assignment]

        # Filter priority emails (urgent + normal) that haven't been replied to — Requirement 2.1
        priority_emails = [
            e for e in all_emails if e.classification in ("urgent", "normal") and not e.is_replied
        ]

        # ----------------------------------------------------------------
        # Fetch pending reply drafts from the database
        # ----------------------------------------------------------------
        pending_replies = await self._get_pending_replies(user_id)

        # ----------------------------------------------------------------
        # Build suggested actions list
        # ----------------------------------------------------------------
        suggested_actions = self._build_suggested_actions(
            priority_emails=priority_emails,
            followup_suggestions=followup_suggestions,
        )

        followup_count = len(followup_suggestions)

        logger.info(
            "Dashboard built for user %s: %d priority emails, %d pending replies, "
            "%d follow-ups, %d suggested actions.",
            user_id,
            len(priority_emails),
            len(pending_replies),
            followup_count,
            len(suggested_actions),
        )

        return DashboardPayload(
            priority_emails=priority_emails,
            pending_replies=pending_replies,
            suggested_actions=suggested_actions,
            followup_count=followup_count,
            analytics=analytics_stats,
        )

    # ------------------------------------------------------------------
    # process_email_action
    # ------------------------------------------------------------------

    async def process_email_action(
        self,
        user_id: str,
        email_id: str,
        action: ActionType,
    ) -> ActionResult:
        """
        Process an email-related action, enforcing the user's execution mode.

        Execution mode enforcement (Requirements 10.1, 10.2, 10.3):
        - suggest:  Return the action as a suggestion only. Do NOT execute.
        - approval: Return the action requiring user confirmation. Do NOT execute.
        - auto:     Execute the action immediately and record analytics.

        Supported actions:
        - "generate_reply": Generate an AI reply draft for the email.
        - "send_reply":     Send an existing pending draft (auto mode only).
        - "create_event":   Suggest meeting times from the email (auto mode only).
        - "send_followup":  Trigger a follow-up check and return suggestions.

        Args:
            user_id: UUID string of the user.
            email_id: UUID string of the email to act on.
            action: One of the supported ActionType literals.

        Returns:
            ActionResult describing what happened and any produced data.

        Requirements: 10.1, 10.2, 10.3
        """
        execution_mode = await self.get_execution_mode(user_id)

        logger.info(
            "process_email_action: user=%s, email=%s, action=%s, mode=%s",
            user_id,
            email_id,
            action,
            execution_mode,
        )

        # ----------------------------------------------------------------
        # suggest mode — present as suggestion, do NOT execute
        # ----------------------------------------------------------------
        if execution_mode == "suggest":
            return ActionResult(
                action=action,
                status="suggested",
                execution_mode=execution_mode,
                data={"email_id": email_id, "action": action},
                message=(
                    f"Action '{action}' is presented as a suggestion. "
                    "Confirm to execute."
                ),
            )

        # ----------------------------------------------------------------
        # approval mode — require explicit confirmation, do NOT execute
        # ----------------------------------------------------------------
        if execution_mode == "approval":
            return ActionResult(
                action=action,
                status="pending_approval",
                execution_mode=execution_mode,
                data={"email_id": email_id, "action": action},
                message=(
                    f"Action '{action}' requires explicit user approval before execution."
                ),
            )

        # ----------------------------------------------------------------
        # auto mode — execute immediately (Requirement 10.3)
        # ----------------------------------------------------------------
        try:
            data = await self._execute_action(user_id, email_id, action)
            return ActionResult(
                action=action,
                status="executed",
                execution_mode=execution_mode,
                data=data,
                message=f"Action '{action}' executed automatically.",
            )
        except Exception as exc:
            logger.error(
                "Auto-execution of action '%s' failed for user %s, email %s: %s",
                action,
                user_id,
                email_id,
                exc,
            )
            return ActionResult(
                action=action,
                status="error",
                execution_mode=execution_mode,
                data=None,
                message=f"Action '{action}' failed: {exc}",
            )

    # ------------------------------------------------------------------
    # run_followup_check
    # ------------------------------------------------------------------

    async def run_followup_check(self, user_id: str) -> list[FollowupSuggestion]:
        """
        Run the follow-up detection check for the user.

        Delegates to FollowupAgent.check_pending_followups() and returns
        the list of pending follow-up suggestions sorted by sent_at ascending.

        Args:
            user_id: UUID string of the user.

        Returns:
            List of FollowupSuggestion objects (may be empty).

        Requirements: 2.1
        """
        logger.info("Running follow-up check for user %s.", user_id)
        try:
            suggestions = await self._followup_agent.check_pending_followups(
                user_id, self._session
            )
            logger.info(
                "Follow-up check complete for user %s: %d suggestion(s).",
                user_id,
                len(suggestions),
            )
            return suggestions
        except Exception as exc:
            logger.error(
                "Follow-up check failed for user %s: %s", user_id, exc
            )
            return []

    # ------------------------------------------------------------------
    # generate_daily_brief
    # ------------------------------------------------------------------

    async def generate_daily_brief(self, user_id: str) -> DailyBrief:
        """
        Generate an AI daily brief for the user.

        Gathers context from:
        - Urgent emails (fetched from EmailService)
        - Pending follow-ups (from FollowupAgent)
        - Upcoming calendar events for the next 2 days (from CalendarService)
        - Current analytics stats (from AnalyticsService)

        Then calls DecisionEngine.generate_daily_brief() with the assembled
        BriefContext. Handles partial failures by using empty defaults for
        any unavailable service.

        Args:
            user_id: UUID string of the user.

        Returns:
            DailyBrief with exactly 3 urgent items, 2 follow-ups, and 1 risk.

        Requirements: 2.1, 8.4 (Requirement 8.4 — gather context from all sources)
        """
        logger.info("Generating daily brief for user %s.", user_id)

        # Gather context sequentially to avoid asyncpg InterfaceError on shared session
        try:
            emails_result = await self._email_svc.fetch_emails(user_id)
        except Exception as e:
            emails_result = e
            
        try:
            followup_result = await self._followup_agent.check_pending_followups(user_id, self._session)
        except Exception as e:
            followup_result = e
            
        try:
            events_result = await self._calendar_svc.get_upcoming_events(user_id, days=2)
        except Exception as e:
            events_result = e
            
        try:
            analytics_result = await self._analytics_svc.get_dashboard_stats(user_id)
        except Exception as e:
            analytics_result = e

        # Handle partial failures
        if isinstance(emails_result, Exception):
            logger.error(
                "Email service failed during brief generation for user %s: %s",
                user_id,
                emails_result,
            )
            all_emails: list[EmailMessage] = []
        else:
            all_emails = emails_result  # type: ignore[assignment]

        if isinstance(followup_result, Exception):
            logger.error(
                "Followup agent failed during brief generation for user %s: %s",
                user_id,
                followup_result,
            )
            followup_suggestions: list[FollowupSuggestion] = []
        else:
            followup_suggestions = followup_result  # type: ignore[assignment]

        if isinstance(events_result, Exception):
            logger.error(
                "Calendar service failed during brief generation for user %s: %s",
                user_id,
                events_result,
            )
            upcoming_events = []
        else:
            upcoming_events = events_result  # type: ignore[assignment]

        if isinstance(analytics_result, Exception):
            logger.error(
                "Analytics service failed during brief generation for user %s: %s",
                user_id,
                analytics_result,
            )
            analytics_stats = AnalyticsStats(
                actions_automated=0,
                time_saved_minutes=0.0,
                emails_classified=0,
                replies_sent=0,
                events_created=0,
            )
        else:
            analytics_stats = analytics_result  # type: ignore[assignment]

        # Filter to urgent emails only for the brief context
        urgent_emails = [e for e in all_emails if e.classification == "urgent"]

        brief_context = BriefContext(
            urgent_emails=urgent_emails,
            pending_followups=followup_suggestions,
            upcoming_events=upcoming_events,
            analytics_stats=analytics_stats,
        )

        brief = await self._decision.generate_daily_brief(brief_context)

        logger.info("Daily brief generated for user %s.", user_id)
        return brief

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_pending_replies(self, user_id: str) -> list[ReplyDraft]:
        """
        Fetch all reply drafts with status="pending" for the user from the DB.

        Args:
            user_id: UUID string of the user.

        Returns:
            List of ReplyDraft Pydantic models.
        """
        user_uuid = UUID(user_id)
        stmt = select(ReplyDraftORM).where(
            ReplyDraftORM.user_id == user_uuid,
            ReplyDraftORM.status == "pending",
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        drafts = [
            ReplyDraft(
                id=row.id,
                email_id=row.email_id,
                draft_text=row.draft_text,
                status=row.status,
            )
            for row in rows
            if row.email_id is not None
        ]

        logger.debug(
            "Found %d pending reply drafts for user %s.", len(drafts), user_id
        )
        return drafts

    @staticmethod
    def _build_suggested_actions(
        priority_emails: list[EmailMessage],
        followup_suggestions: list[FollowupSuggestion],
    ) -> list[str]:
        """
        Build a list of human-readable suggested action strings.

        Args:
            priority_emails: Filtered list of urgent/normal emails.
            followup_suggestions: Pending follow-up suggestions.

        Returns:
            List of action description strings.
        """
        actions: list[str] = []

        for email in priority_emails:
            subject = email.subject or "(no subject)"
            if email.classification == "urgent":
                actions.append(f"Reply urgently to email from {email.sender}: {subject}")
            else:
                actions.append(f"Reply to email from {email.sender}: {subject}")

        for followup in followup_suggestions:
            subject = followup.subject or "(no subject)"
            actions.append(
                f"Send follow-up to {followup.sender} re: {subject} "
                f"({followup.days_elapsed} days elapsed)"
            )

        return actions

    async def _execute_action(
        self,
        user_id: str,
        email_id: str,
        action: ActionType,
    ) -> Any:
        """
        Execute an action immediately (called only in auto mode).

        Dispatches to the appropriate service method and records analytics.

        Args:
            user_id: UUID string of the user.
            email_id: UUID string of the email.
            action: The action to execute.

        Returns:
            Action-specific result data (dict or list).

        Raises:
            ValueError: If the action type is not recognised.
        """
        if action == "generate_reply":
            draft = await self._email_svc.generate_reply_draft(user_id, email_id)
            # Record analytics for auto-generated reply
            await self._record_analytics_event(
                user_id=user_id,
                event_type="reply_sent",
                metadata={"email_id": email_id, "draft_id": str(draft.id)},
                time_saved_min=5.0,
            )
            return {"draft_id": str(draft.id), "status": draft.status}

        elif action == "send_reply":
            # Fetch the most recent pending draft for this email and send it
            user_uuid = UUID(user_id)
            email_uuid = UUID(email_id)
            stmt = (
                select(ReplyDraftORM)
                .where(
                    ReplyDraftORM.user_id == user_uuid,
                    ReplyDraftORM.email_id == email_uuid,
                    ReplyDraftORM.status == "pending",
                )
                .order_by(ReplyDraftORM.created_at.desc())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            draft_row = result.scalar_one_or_none()

            if draft_row is None:
                raise ValueError(
                    f"No pending draft found for email {email_id}. "
                    "Generate a reply first."
                )

            send_result = await self._email_svc.send_reply(user_id, str(draft_row.id))
            return send_result

        elif action == "create_event":
            email = await self._email_svc.get_email(user_id, email_id)
            meeting_slots = await self._calendar_svc.suggest_meeting_times(
                user_id, email
            )
            # Record analytics for auto-created event suggestion
            await self._record_analytics_event(
                user_id=user_id,
                event_type="event_created",
                metadata={"email_id": email_id, "slots_suggested": len(meeting_slots)},
                time_saved_min=10.0,
            )
            return {
                "meeting_slots": [
                    {
                        "start": slot.slot.start.isoformat(),
                        "end": slot.slot.end.isoformat(),
                        "confidence_score": slot.confidence_score,
                        "reason": slot.reason,
                    }
                    for slot in meeting_slots
                ]
            }

        elif action == "send_followup":
            followups = await self._followup_agent.check_pending_followups(
                user_id, self._session
            )
            # Record analytics for auto-triggered follow-up
            await self._record_analytics_event(
                user_id=user_id,
                event_type="followup_sent",
                metadata={"email_id": email_id, "followups_found": len(followups)},
                time_saved_min=5.0,
            )
            return {
                "followups_triggered": len(followups),
                "followup_ids": [str(f.id) for f in followups],
            }

        else:
            raise ValueError(f"Unknown action type: {action!r}")

    async def _record_analytics_event(
        self,
        user_id: str,
        event_type: str,
        metadata: dict | None = None,
        time_saved_min: float = 0.0,
    ) -> None:
        """
        Record an analytics event, swallowing any errors to avoid disrupting
        the main action flow.

        Args:
            user_id: UUID string of the user.
            event_type: Analytics event type string.
            metadata: Optional metadata dict.
            time_saved_min: Estimated time saved in minutes.
        """
        try:
            user_uuid = UUID(user_id)
            event = AnalyticsEvent(
                id=uuid.uuid4(),
                user_id=user_uuid,
                event_type=event_type,  # type: ignore[arg-type]
                metadata=metadata,
                time_saved_min=time_saved_min,
                created_at=datetime.now(tz=timezone.utc),
            )
            await self._analytics_svc.record_event(user_id, event)
        except Exception as exc:
            logger.warning(
                "Failed to record analytics event '%s' for user %s: %s",
                event_type,
                user_id,
                exc,
            )
