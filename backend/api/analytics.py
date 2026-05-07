"""
Analytics API router — productivity metrics endpoints.

Routes:
    GET /analytics/stats       → aggregated dashboard stats (Req 11.1–11.4)
    GET /analytics/time-saved  → total time saved in minutes (Req 11.3)
    GET /analytics/actions     → per-event-type action counts (Req 11.4)

Requirements: 11.1, 11.2, 11.3, 11.4
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, get_db
from backend.schemas.pydantic_schemas import AnalyticsStats, DailyMetrics, User
from backend.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/stats",
    response_model=AnalyticsStats,
    summary="Get aggregated productivity stats",
)
async def get_stats(
    period: str = "week",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsStats:
    """
    Return aggregated productivity metrics for the authenticated user.

    Query params:
        period: "week" (last 7 days, default) or "month" (last 30 days).

    Response fields:
        - actions_automated: reply_sent + event_created + followup_sent
        - time_saved_minutes: replies * 5 min + events * 10 min
        - emails_classified: total emails classified
        - replies_sent: total automated replies sent
        - events_created: total calendar events created

    Requirements: 11.1, 11.2, 11.3, 11.4
    """
    user_id = str(current_user.id)
    analytics_service = AnalyticsService(db)

    stats = await analytics_service.get_dashboard_stats(user_id, period)

    logger.info(
        "GET /analytics/stats — user=%s, period=%s, actions_automated=%d, "
        "time_saved=%.1f min",
        user_id,
        period,
        stats.actions_automated,
        stats.time_saved_minutes,
    )
    return stats


@router.get(
    "/time-saved",
    summary="Get total time saved in minutes",
)
async def get_time_saved(
    period: str = "week",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return the total estimated time saved (in minutes) for the given period.

    Time-saved constants:
        - reply_sent  → 5 minutes
        - event_created → 10 minutes

    Query params:
        period: "week" (last 7 days, default) or "month" (last 30 days).

    Requirements: 11.3
    """
    user_id = str(current_user.id)
    analytics_service = AnalyticsService(db)

    time_saved = await analytics_service.get_time_saved(user_id, period)

    logger.info(
        "GET /analytics/time-saved — user=%s, period=%s, time_saved=%.1f min",
        user_id,
        period,
        time_saved,
    )
    return {"time_saved_minutes": time_saved}


@router.get(
    "/actions",
    summary="Get per-event-type action counts",
)
async def get_actions(
    period: str = "week",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """
    Return a mapping of event_type → count for the given period.

    Query params:
        period: "week" (last 7 days, default) or "month" (last 30 days).

    Requirements: 11.4
    """
    user_id = str(current_user.id)
    analytics_service = AnalyticsService(db)

    counts = await analytics_service.get_action_counts(user_id, period)

    logger.info(
        "GET /analytics/actions — user=%s, period=%s, counts=%s",
        user_id,
        period,
        counts,
    )
    return counts


@router.get(
    "/daily",
    response_model=list[DailyMetrics],
    summary="Get daily activity counts for charts",
)
async def get_daily(
    period: str = "week",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DailyMetrics]:
    """
    Return daily activity counts (replies, events, classifications) for the user.

    Query params:
        period: "week" (last 7 days, default) or "month" (last 30 days).
    """
    from backend.schemas.pydantic_schemas import DailyMetrics

    user_id = str(current_user.id)
    analytics_service = AnalyticsService(db)

    metrics = await analytics_service.get_daily_metrics(user_id, period)
    return metrics
