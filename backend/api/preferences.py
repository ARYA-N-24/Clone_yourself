"""
Preferences API router — user settings endpoints.

Routes:
    GET  /preferences → fetch current user's preferences
    PUT  /preferences → update current user's preferences

Requirements: 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, get_db
from models.db_models import UserPreference
from schemas.pydantic_schemas import User, UserPreferences

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=UserPreferences,
    summary="Fetch current user's preferences",
)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPreferences:
    """
    Return the behavioral preferences for the authenticated user.
    If no preferences exist in the DB, returns default values.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    prefs = result.scalar_one_or_none()

    if not prefs:
        logger.debug("No preferences found for user %s; returning defaults.", current_user.id)
        return UserPreferences()

    return UserPreferences.model_validate(prefs)


@router.put(
    "",
    response_model=UserPreferences,
    summary="Update current user's preferences",
)
async def update_preferences(
    body: UserPreferences,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserPreferences:
    """
    Update (or create) behavioral preferences for the authenticated user.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    prefs = result.scalar_one_or_none()

    if not prefs:
        logger.info("Creating new preferences record for user %s.", current_user.id)
        prefs = UserPreference(user_id=current_user.id)
        db.add(prefs)

    # Update fields
    prefs.tone = body.tone
    prefs.working_hours_start = body.working_hours_start
    prefs.working_hours_end = body.working_hours_end
    prefs.working_days = body.working_days
    prefs.meeting_duration = body.meeting_duration
    prefs.followup_threshold = body.followup_threshold
    prefs.execution_mode = body.execution_mode

    await db.commit()
    await db.refresh(prefs)

    logger.info("Updated preferences for user %s.", current_user.id)
    return UserPreferences.model_validate(prefs)
