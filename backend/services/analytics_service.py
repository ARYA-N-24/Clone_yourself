"""
Analytics Service for the Clone Yourself Platform.

Tracks automated actions and computes productivity metrics.

Interface:
    - record_event(user_id, event) → None
    - get_dashboard_stats(user_id) → AnalyticsStats
    - get_time_saved(user_id, period) → float
    - get_action_counts(user_id, period) → dict[str, int]

Requirements: 11.1, 11.2, 11.3, 11.4
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.db_models import AnalyticsEvent as AnalyticsEventORM
from backend.schemas.pydantic_schemas import AnalyticsEvent, AnalyticsStats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Time-saved constants (minutes per automated action)
# ---------------------------------------------------------------------------

TIME_SAVED_PER_REPLY = 5.0   # minutes
TIME_SAVED_PER_EVENT = 10.0  # minutes

# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_PERIOD_DAYS: dict[str, int] = {
    "week": 7,
    "month": 30,
}


def _period_start(period: str) -> datetime:
    """Return the UTC datetime marking the start of the requested period."""
    days = _PERIOD_DAYS.get(period, _PERIOD_DAYS["week"])
    return datetime.utcnow() - timedelta(days=days)


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------


class AnalyticsService:
    """
    Tracks automated actions and computes productivity metrics.

    Args:
        session: SQLAlchemy AsyncSession for database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # record_event
    # ------------------------------------------------------------------

    async def record_event(self, user_id: str, event: AnalyticsEvent) -> None:
        """
        Insert an analytics event row into the database.

        Args:
            user_id: UUID string of the user.
            event: AnalyticsEvent Pydantic schema instance to persist.

        Requirements: 11.1
        """
        user_uuid = UUID(user_id)

        orm_event = AnalyticsEventORM(
            id=event.id,
            user_id=user_uuid,
            event_type=event.event_type,
            metadata_=event.metadata,
            time_saved_min=event.time_saved_min,
            created_at=event.created_at,
        )

        self._session.add(orm_event)
        await self._session.commit()

        logger.info(
            "Recorded analytics event '%s' for user %s.", event.event_type, user_id
        )

    # ------------------------------------------------------------------
    # get_dashboard_stats
    # ------------------------------------------------------------------

    async def get_dashboard_stats(
        self, user_id: str, period: str = "week"
    ) -> AnalyticsStats:
        """
        Compute aggregated productivity metrics for the dashboard.

        Counts are computed over the requested period (default: last 7 days).

        Metrics:
            - actions_automated = reply_sent + event_created + followup_sent
            - time_saved_minutes = reply_sent * 5 + event_created * 10
            - emails_classified = COUNT(email_classified)
            - replies_sent = COUNT(reply_sent)
            - events_created = COUNT(event_created)

        Args:
            user_id: UUID string of the user.
            period: "week" (last 7 days) or "month" (last 30 days).

        Returns:
            AnalyticsStats with aggregated metrics.

        Requirements: 11.2, 11.3
        """
        user_uuid = UUID(user_id)
        since = _period_start(period)

        # Fetch per-event-type counts in a single query using conditional aggregation
        stmt = (
            select(
                func.count()
                .filter(AnalyticsEventORM.event_type == "reply_sent")
                .label("replies_sent"),
                func.count()
                .filter(AnalyticsEventORM.event_type == "event_created")
                .label("events_created"),
                func.count()
                .filter(AnalyticsEventORM.event_type == "followup_sent")
                .label("followups_sent"),
                func.count()
                .filter(AnalyticsEventORM.event_type == "email_classified")
                .label("emails_classified"),
            )
            .where(
                AnalyticsEventORM.user_id == user_uuid,
                AnalyticsEventORM.created_at >= since,
            )
        )

        result = await self._session.execute(stmt)
        row = result.one()

        replies_sent: int = row.replies_sent or 0
        events_created: int = row.events_created or 0
        followups_sent: int = row.followups_sent or 0
        emails_classified: int = row.emails_classified or 0

        actions_automated = replies_sent + events_created + followups_sent
        time_saved_minutes = (
            replies_sent * TIME_SAVED_PER_REPLY
            + events_created * TIME_SAVED_PER_EVENT
        )

        logger.debug(
            "Dashboard stats for user %s (%s): automated=%d, time_saved=%.1f min",
            user_id,
            period,
            actions_automated,
            time_saved_minutes,
        )

        return AnalyticsStats(
            actions_automated=actions_automated,
            time_saved_minutes=time_saved_minutes,
            emails_classified=emails_classified,
            replies_sent=replies_sent,
            events_created=events_created,
        )

    # ------------------------------------------------------------------
    # get_time_saved
    # ------------------------------------------------------------------

    async def get_time_saved(self, user_id: str, period: str = "week") -> float:
        """
        Return total estimated time saved (in minutes) for the given period.

        Uses the same constants as get_dashboard_stats:
            - reply_sent  → 5 min
            - event_created → 10 min

        Args:
            user_id: UUID string of the user.
            period: "week" (last 7 days) or "month" (last 30 days).

        Returns:
            Total time saved in minutes as a float.

        Requirements: 11.3
        """
        user_uuid = UUID(user_id)
        since = _period_start(period)

        stmt = (
            select(
                func.count()
                .filter(AnalyticsEventORM.event_type == "reply_sent")
                .label("replies_sent"),
                func.count()
                .filter(AnalyticsEventORM.event_type == "event_created")
                .label("events_created"),
            )
            .where(
                AnalyticsEventORM.user_id == user_uuid,
                AnalyticsEventORM.created_at >= since,
            )
        )

        result = await self._session.execute(stmt)
        row = result.one()

        replies_sent: int = row.replies_sent or 0
        events_created: int = row.events_created or 0

        time_saved = (
            replies_sent * TIME_SAVED_PER_REPLY
            + events_created * TIME_SAVED_PER_EVENT
        )

        logger.debug(
            "Time saved for user %s (%s): %.1f min", user_id, period, time_saved
        )

        return time_saved

    # ------------------------------------------------------------------
    # get_action_counts
    # ------------------------------------------------------------------

    async def get_action_counts(
        self, user_id: str, period: str = "week"
    ) -> dict[str, int]:
        """
        Return a mapping of event_type → count for the given period.

        Args:
            user_id: UUID string of the user.
            period: "week" (last 7 days) or "month" (last 30 days).

        Returns:
            Dict mapping each event_type string to its occurrence count.

        Requirements: 11.4
        """
        user_uuid = UUID(user_id)
        since = _period_start(period)

        stmt = (
            select(
                AnalyticsEventORM.event_type,
                func.count().label("cnt"),
            )
            .where(
                AnalyticsEventORM.user_id == user_uuid,
                AnalyticsEventORM.created_at >= since,
            )
            .group_by(AnalyticsEventORM.event_type)
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        counts: dict[str, int] = {row.event_type: row.cnt for row in rows}

        logger.debug(
            "Action counts for user %s (%s): %s", user_id, period, counts
        )

        return counts
