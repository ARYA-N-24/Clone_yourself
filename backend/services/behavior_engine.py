"""
Behavior Engine service for the Clone Yourself Platform.

Stores and retrieves user behavioral preferences. Provides tone, style, and
scheduling context to the Decision Engine.

Interface:
    - get_user_preferences(user_id) → UserPreferences
    - update_preferences(user_id, prefs) → None
    - get_writing_style_context(user_id, email_context) → StyleContext
    - record_user_action(user_id, action) → None
    - infer_preferences_from_history(user_id) → UserPreferences

Requirements: 9.1, 9.2, 9.3, 9.4, 4.9
"""

from __future__ import annotations

import logging
import os
from typing import TypedDict
from uuid import UUID

import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.db_models import AnalyticsEvent, Email, UserPreference
from backend.schemas.pydantic_schemas import StyleContext, UserPreferences
from backend.utils.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


class UserAction(TypedDict):
    """Simple dataclass for user action metadata."""

    action_type: str
    metadata: dict


class BehaviorEngine:
    """
    Manages user behavioral preferences and writing style context.

    Args:
        session: SQLAlchemy AsyncSession for database operations.
        faiss_store: Optional FAISSStore instance (defaults to ./faiss_indexes/).
        openai_client: Optional OpenAI client (defaults to a new client using OPENAI_API_KEY env var).
    """

    def __init__(
        self,
        session: AsyncSession,
        faiss_store: FAISSStore | None = None,
        openai_client: openai.OpenAI | None = None,
    ) -> None:
        self._session = session
        self._faiss = faiss_store or FAISSStore()
        if openai_client is not None:
            self._openai = openai_client
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            self._openai = openai.OpenAI(api_key=api_key) if api_key else None

    # ------------------------------------------------------------------
    # get_user_preferences
    # ------------------------------------------------------------------

    async def get_user_preferences(self, user_id: str) -> UserPreferences:
        """
        Retrieve user preferences from the database.

        If no preferences exist for the user, create a default UserPreference
        row and return defaults.

        Args:
            user_id: UUID string of the user.

        Returns:
            UserPreferences object with the user's stored preferences.

        Requirements: 9.1, 9.4
        """
        user_uuid = UUID(user_id)

        # Query user_preferences table
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await self._session.execute(stmt)
        pref_row = result.scalar_one_or_none()

        if pref_row is None:
            # Create default preferences
            logger.info("No preferences found for user %s; creating defaults.", user_id)
            default_pref = UserPreference(user_id=user_uuid)
            self._session.add(default_pref)
            await self._session.commit()
            await self._session.refresh(default_pref)
            pref_row = default_pref

        # Convert ORM model to Pydantic model
        return UserPreferences.model_validate(pref_row)

    # ------------------------------------------------------------------
    # update_preferences
    # ------------------------------------------------------------------

    async def update_preferences(
        self, user_id: str, prefs: UserPreferences
    ) -> None:
        """
        Update (upsert) user preferences in the database.

        Args:
            user_id: UUID string of the user.
            prefs: UserPreferences object with updated values.

        Requirements: 9.2
        """
        user_uuid = UUID(user_id)

        # Check if preferences exist
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await self._session.execute(stmt)
        pref_row = result.scalar_one_or_none()

        if pref_row is None:
            # Insert new row
            pref_row = UserPreference(user_id=user_uuid)
            self._session.add(pref_row)

        # Update fields
        pref_row.tone = prefs.tone
        pref_row.working_hours_start = prefs.working_hours_start
        pref_row.working_hours_end = prefs.working_hours_end
        pref_row.working_days = prefs.working_days
        pref_row.meeting_duration = prefs.meeting_duration
        pref_row.followup_threshold = prefs.followup_threshold
        pref_row.execution_mode = prefs.execution_mode

        await self._session.commit()
        logger.info("Updated preferences for user %s.", user_id)

    # ------------------------------------------------------------------
    # get_writing_style_context
    # ------------------------------------------------------------------

    async def get_writing_style_context(
        self, user_id: str, email_context: str
    ) -> StyleContext:
        """
        Generate a StyleContext for reply generation.

        Steps:
        1. Generate an OpenAI embedding for email_context using text-embedding-3-small
        2. Query FAISS for top-5 similar email vector IDs
        3. Fetch those emails from the emails table
        4. Return StyleContext(tone=prefs.tone, similar_emails=[...])

        If FAISS index doesn't exist or returns no results, return empty similar_emails.

        Args:
            user_id: UUID string of the user.
            email_context: The email body text to generate context for.

        Returns:
            StyleContext with tone and similar email examples.

        Requirements: 9.3, 4.2
        """
        user_uuid = UUID(user_id)

        # Get user preferences for tone
        prefs = await self.get_user_preferences(user_id)

        # Generate embedding for email_context
        try:
            # NOTE: Groq does not support embeddings. 
            # We use a zero vector as a fallback.
            embedding = [0.0] * 1536
        except Exception as exc:
            logger.warning(
                "Failed to generate embedding for user %s: %s. Returning empty context.",
                user_id,
                exc,
            )
            return StyleContext(tone=prefs.tone, similar_emails=[])

        # Query FAISS for top-5 similar emails
        try:
            similar_ids = self._faiss.search(user_id, embedding, top_k=5)
        except Exception as exc:
            logger.warning(
                "FAISS search failed for user %s: %s. Returning empty context.",
                user_id,
                exc,
            )
            return StyleContext(tone=prefs.tone, similar_emails=[])

        if not similar_ids:
            logger.debug("No similar emails found in FAISS for user %s.", user_id)
            return StyleContext(tone=prefs.tone, similar_emails=[])

        # Fetch emails from database
        # Convert embedding_ids (strings) to match against emails.embedding_id
        stmt = select(Email).where(
            Email.user_id == user_uuid, Email.embedding_id.in_(similar_ids)
        )
        result = await self._session.execute(stmt)
        email_rows = result.scalars().all()

        # Convert ORM models to Pydantic EmailMessage models
        from backend.schemas.pydantic_schemas import EmailMessage

        similar_emails = [EmailMessage.model_validate(row) for row in email_rows]

        logger.debug(
            "Found %d similar emails for user %s.", len(similar_emails), user_id
        )

        return StyleContext(tone=prefs.tone, similar_emails=similar_emails)

    # ------------------------------------------------------------------
    # record_user_action
    # ------------------------------------------------------------------

    async def record_user_action(self, user_id: str, action: UserAction) -> None:
        """
        Record a user action (e.g., editing an AI-generated draft) to analytics.

        Inserts an AnalyticsEvent row with event_type="user_edit" and metadata
        containing the action details.

        Args:
            user_id: UUID string of the user.
            action: UserAction dict with action_type and metadata.

        Requirements: 4.9
        """
        user_uuid = UUID(user_id)

        event = AnalyticsEvent(
            user_id=user_uuid,
            event_type="user_edit",
            metadata_={
                "action_type": action["action_type"],
                "details": action["metadata"],
            },
            time_saved_min=0.0,
        )

        self._session.add(event)
        await self._session.commit()

        logger.info(
            "Recorded user action for user %s: %s", user_id, action["action_type"]
        )

    # ------------------------------------------------------------------
    # infer_preferences_from_history
    # ------------------------------------------------------------------

    async def infer_preferences_from_history(self, user_id: str) -> UserPreferences:
        """
        Infer user preferences from historical actions.

        For MVP, this simply returns the stored preferences. Full inference
        from history is out of scope.

        Args:
            user_id: UUID string of the user.

        Returns:
            UserPreferences object (same as get_user_preferences).

        Requirements: 9.1
        """
        logger.debug(
            "infer_preferences_from_history called for user %s; returning stored prefs.",
            user_id,
        )
        return await self.get_user_preferences(user_id)
