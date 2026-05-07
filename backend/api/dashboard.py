"""
Dashboard API router — unified dashboard endpoint.

Routes:
    GET /dashboard → aggregate and return DashboardPayload (Req 2.1–2.4)

Requirements: 2.1, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import logging
import os

import openai
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, get_db
from backend.schemas.pydantic_schemas import DashboardPayload, User
from backend.services.analytics_service import AnalyticsService
from backend.services.behavior_engine import BehaviorEngine
from backend.services.calendar_service import CalendarService
from backend.services.decision_engine import DecisionEngine
from backend.services.email_service import EmailService
from backend.services.followup_agent import FollowupAgent
from backend.services.task_orchestrator import TaskOrchestrator
from backend.utils.faiss_store import FAISSStore

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _make_task_orchestrator(session: AsyncSession) -> TaskOrchestrator:
    """
    Instantiate TaskOrchestrator with all required service dependencies.

    Uses environment variables for the OpenAI API key.
    FAISSStore defaults to the ./faiss_indexes/ directory.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    openai_sync_client = openai.OpenAI(api_key=api_key)
    openai_async_client = openai.AsyncOpenAI(api_key=api_key)

    faiss_store = FAISSStore()
    analytics_service = AnalyticsService(session)
    behavior_engine = BehaviorEngine(
        session=session,
        faiss_store=faiss_store,
        openai_client=openai_sync_client,
    )
    decision_engine = DecisionEngine(
        openai_client=openai_async_client,
        session=session,
    )
    email_service = EmailService(
        session=session,
        faiss_store=faiss_store,
        openai_client=openai_sync_client,
        decision_engine=decision_engine,
        behavior_engine=behavior_engine,
        analytics_service=analytics_service,
    )
    calendar_service = CalendarService(
        session=session,
        decision_engine=decision_engine,
        openai_client=openai_sync_client,
    )
    followup_agent = FollowupAgent(decision_engine=decision_engine)

    return TaskOrchestrator(
        session=session,
        email_service=email_service,
        calendar_service=calendar_service,
        followup_agent=followup_agent,
        analytics_service=analytics_service,
        behavior_engine=behavior_engine,
        decision_engine=decision_engine,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=DashboardPayload,
    summary="Get aggregated dashboard data",
)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardPayload:
    """
    Return the full dashboard payload for the authenticated user.

    Delegates to ``TaskOrchestrator.get_dashboard()`` which fetches data
    concurrently (Req 2.4) and handles partial service failures gracefully
    (Req 2.2).

    The response includes:
    - ``priority_emails``: urgent and normal emails (Req 2.1)
    - ``pending_replies``: reply drafts awaiting action
    - ``suggested_actions``: human-readable action strings
    - ``followup_count``: number of pending follow-ups (Req 2.3)
    - ``analytics``: aggregated productivity stats (Req 2.1)

    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    user_id = str(current_user.id)
    orchestrator = _make_task_orchestrator(db)

    payload = await orchestrator.get_dashboard(user_id)

    logger.info(
        "GET /dashboard — user=%s, priority_emails=%d, pending_replies=%d, "
        "followup_count=%d, suggested_actions=%d",
        user_id,
        len(payload.priority_emails),
        len(payload.pending_replies),
        payload.followup_count,
        len(payload.suggested_actions),
    )
    return payload
