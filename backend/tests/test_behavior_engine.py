"""
Unit tests for backend/services/behavior_engine.py

Covers:
- get_user_preferences: returns stored preferences; creates defaults if none exist
- update_preferences: upserts preferences correctly
- get_writing_style_context: generates embeddings, queries FAISS, returns StyleContext
- record_user_action: inserts AnalyticsEvent with event_type="user_edit"
- infer_preferences_from_history: returns stored preferences (MVP behavior)

Requirements: 9.1, 9.2, 9.3, 9.4, 4.9
"""

import asyncio
import uuid
from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.db_models import AnalyticsEvent, UserPreference
from schemas.pydantic_schemas import UserPreferences
from services.behavior_engine import BehaviorEngine, UserAction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_id() -> str:
    return str(uuid.uuid4())


def _make_mock_session():
    """Return a mock AsyncSession with common async methods."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _make_pref_mock(tone="casual", **kwargs) -> MagicMock:
    """Create a MagicMock that looks like a UserPreference ORM row."""
    pref = MagicMock(spec=UserPreference)
    pref.tone = tone
    pref.working_hours_start = kwargs.get("working_hours_start", time(9, 0))
    pref.working_hours_end = kwargs.get("working_hours_end", time(18, 0))
    pref.working_days = kwargs.get("working_days", [1, 2, 3, 4, 5])
    pref.meeting_duration = kwargs.get("meeting_duration", 30)
    pref.followup_threshold = kwargs.get("followup_threshold", 3)
    pref.execution_mode = kwargs.get("execution_mode", "suggest")
    return pref


# ---------------------------------------------------------------------------
# get_user_preferences
# ---------------------------------------------------------------------------


class TestGetUserPreferences:
    def test_returns_stored_preferences(self):
        """When preferences exist, return them."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(
            tone="formal",
            working_hours_start=time(8, 0),
            working_hours_end=time(17, 0),
            meeting_duration=45,
            followup_threshold=5,
            execution_mode="approval",
        )

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.get_user_preferences(user_id))

        assert result.tone == "formal"
        assert result.working_hours_start == time(8, 0)
        assert result.working_hours_end == time(17, 0)
        assert result.meeting_duration == 45
        assert result.followup_threshold == 5
        assert result.execution_mode == "approval"

    def test_creates_defaults_when_none_exist(self):
        """When no preferences exist, create and return defaults."""
        user_id = _make_user_id()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        # After refresh, the pref row should have default values
        async def mock_refresh(obj):
            obj.tone = "casual"
            obj.working_hours_start = time(9, 0)
            obj.working_hours_end = time(18, 0)
            obj.working_days = [1, 2, 3, 4, 5]
            obj.meeting_duration = 30
            obj.followup_threshold = 3
            obj.execution_mode = "suggest"

        session.refresh = mock_refresh

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.get_user_preferences(user_id))

        assert result.tone == "casual"
        assert result.working_hours_start == time(9, 0)
        assert result.working_hours_end == time(18, 0)
        assert result.working_days == [1, 2, 3, 4, 5]
        assert result.meeting_duration == 30
        assert result.followup_threshold == 3
        assert result.execution_mode == "suggest"

    def test_adds_default_row_to_session(self):
        """When no preferences exist, a new UserPreference is added to the session."""
        user_id = _make_user_id()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        async def mock_refresh(obj):
            obj.tone = "casual"
            obj.working_hours_start = time(9, 0)
            obj.working_hours_end = time(18, 0)
            obj.working_days = [1, 2, 3, 4, 5]
            obj.meeting_duration = 30
            obj.followup_threshold = 3
            obj.execution_mode = "suggest"

        session.refresh = mock_refresh

        engine = BehaviorEngine(session)
        asyncio.run(engine.get_user_preferences(user_id))

        # Verify that session.add was called with a UserPreference
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, UserPreference)

    def test_returns_user_preferences_type(self):
        """Return type is always UserPreferences."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.get_user_preferences(user_id))

        assert isinstance(result, UserPreferences)


# ---------------------------------------------------------------------------
# update_preferences
# ---------------------------------------------------------------------------


class TestUpdatePreferences:
    def test_updates_existing_preferences(self):
        """When preferences exist, update them."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        new_prefs = UserPreferences(
            tone="formal",
            working_hours_start=time(7, 0),
            working_hours_end=time(16, 0),
            working_days=[1, 2, 3],
            meeting_duration=60,
            followup_threshold=7,
            execution_mode="auto",
        )

        asyncio.run(engine.update_preferences(user_id, new_prefs))

        # Verify the row was updated
        assert pref_row.tone == "formal"
        assert pref_row.working_hours_start == time(7, 0)
        assert pref_row.working_hours_end == time(16, 0)
        assert pref_row.working_days == [1, 2, 3]
        assert pref_row.meeting_duration == 60
        assert pref_row.followup_threshold == 7
        assert pref_row.execution_mode == "auto"

        # Verify commit was called
        session.commit.assert_called_once()

    def test_creates_preferences_when_none_exist(self):
        """When no preferences exist, insert a new row."""
        user_id = _make_user_id()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        new_prefs = UserPreferences(tone="formal", execution_mode="approval")

        asyncio.run(engine.update_preferences(user_id, new_prefs))

        # Verify session.add was called with a new UserPreference
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, UserPreference)
        assert added_obj.tone == "formal"
        assert added_obj.execution_mode == "approval"

    def test_all_fields_are_updated(self):
        """All preference fields are updated, not just tone."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        new_prefs = UserPreferences(
            tone="formal",
            working_hours_start=time(8, 30),
            working_hours_end=time(17, 30),
            working_days=[1, 2, 3, 4],
            meeting_duration=45,
            followup_threshold=2,
            execution_mode="auto",
        )

        asyncio.run(engine.update_preferences(user_id, new_prefs))

        assert pref_row.tone == "formal"
        assert pref_row.working_hours_start == time(8, 30)
        assert pref_row.working_hours_end == time(17, 30)
        assert pref_row.working_days == [1, 2, 3, 4]
        assert pref_row.meeting_duration == 45
        assert pref_row.followup_threshold == 2
        assert pref_row.execution_mode == "auto"

    def test_commit_is_called(self):
        """Session commit is called after update."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        asyncio.run(engine.update_preferences(user_id, UserPreferences()))

        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_writing_style_context
# ---------------------------------------------------------------------------


class TestGetWritingStyleContext:
    def test_returns_context_with_tone(self):
        """Returns StyleContext with user's tone."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="formal")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = []

        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        result = asyncio.run(
            engine.get_writing_style_context(user_id, "Test email body")
        )

        assert result.tone == "formal"
        assert result.similar_emails == []

    def test_queries_faiss_with_embedding(self):
        """FAISS is queried with the generated embedding and top_k=5."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = []

        test_embedding = [0.5] * 1536

        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=test_embedding)]
        )

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        asyncio.run(engine.get_writing_style_context(user_id, "Test email body"))

        # Verify FAISS was called with the embedding and top_k=5
        mock_faiss.search.assert_called_once_with(user_id, test_embedding, top_k=5)

    def test_handles_openai_failure_gracefully(self):
        """When OpenAI fails, return empty context."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()

        mock_openai = MagicMock()
        mock_openai.embeddings.create.side_effect = Exception("OpenAI error")

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        result = asyncio.run(
            engine.get_writing_style_context(user_id, "Test email body")
        )

        assert result.tone == "casual"
        assert result.similar_emails == []

    def test_handles_faiss_failure_gracefully(self):
        """When FAISS fails, return empty context."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="formal")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()
        mock_faiss.search.side_effect = Exception("FAISS error")

        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        result = asyncio.run(
            engine.get_writing_style_context(user_id, "Test email body")
        )

        assert result.tone == "formal"
        assert result.similar_emails == []

    def test_returns_empty_when_faiss_returns_no_ids(self):
        """When FAISS returns no IDs, return empty similar_emails."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = []

        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        result = asyncio.run(
            engine.get_writing_style_context(user_id, "Test email body")
        )

        assert result.similar_emails == []

    def test_uses_text_embedding_3_small_model(self):
        """OpenAI embedding is generated using text-embedding-3-small."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="casual")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = []

        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        engine = BehaviorEngine(session, faiss_store=mock_faiss, openai_client=mock_openai)
        asyncio.run(engine.get_writing_style_context(user_id, "Test email body"))

        # Verify the correct model was used
        call_kwargs = mock_openai.embeddings.create.call_args[1]
        assert call_kwargs["model"] == "text-embedding-3-small"


# ---------------------------------------------------------------------------
# record_user_action
# ---------------------------------------------------------------------------


class TestRecordUserAction:
    def test_inserts_analytics_event_with_user_edit_type(self):
        """Records user action as an analytics event with event_type='user_edit'."""
        user_id = _make_user_id()

        session = _make_mock_session()
        engine = BehaviorEngine(session)

        action: UserAction = {
            "action_type": "draft_edited",
            "metadata": {"draft_id": "123", "changes": "minor"},
        }

        asyncio.run(engine.record_user_action(user_id, action))

        # Verify session.add was called with an AnalyticsEvent
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, AnalyticsEvent)
        assert added_obj.event_type == "user_edit"

    def test_analytics_event_contains_action_metadata(self):
        """The analytics event metadata contains action_type and details."""
        user_id = _make_user_id()

        session = _make_mock_session()
        engine = BehaviorEngine(session)

        action: UserAction = {
            "action_type": "draft_edited",
            "metadata": {"draft_id": "abc-123", "field": "body"},
        }

        asyncio.run(engine.record_user_action(user_id, action))

        added_obj = session.add.call_args[0][0]
        assert added_obj.metadata_["action_type"] == "draft_edited"
        assert added_obj.metadata_["details"]["draft_id"] == "abc-123"

    def test_analytics_event_time_saved_is_zero(self):
        """User edit actions have time_saved_min = 0."""
        user_id = _make_user_id()

        session = _make_mock_session()
        engine = BehaviorEngine(session)

        action: UserAction = {
            "action_type": "draft_edited",
            "metadata": {},
        }

        asyncio.run(engine.record_user_action(user_id, action))

        added_obj = session.add.call_args[0][0]
        assert added_obj.time_saved_min == 0.0

    def test_commit_is_called_after_insert(self):
        """Session commit is called after inserting the analytics event."""
        user_id = _make_user_id()

        session = _make_mock_session()
        engine = BehaviorEngine(session)

        action: UserAction = {
            "action_type": "draft_edited",
            "metadata": {},
        }

        asyncio.run(engine.record_user_action(user_id, action))

        session.commit.assert_called_once()

    def test_user_id_is_set_on_event(self):
        """The analytics event has the correct user_id."""
        user_id = _make_user_id()
        user_uuid = uuid.UUID(user_id)

        session = _make_mock_session()
        engine = BehaviorEngine(session)

        action: UserAction = {
            "action_type": "draft_edited",
            "metadata": {},
        }

        asyncio.run(engine.record_user_action(user_id, action))

        added_obj = session.add.call_args[0][0]
        assert added_obj.user_id == user_uuid


# ---------------------------------------------------------------------------
# infer_preferences_from_history
# ---------------------------------------------------------------------------


class TestInferPreferencesFromHistory:
    def test_returns_stored_preferences(self):
        """For MVP, returns the same as get_user_preferences."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock(tone="formal", execution_mode="auto")

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.infer_preferences_from_history(user_id))

        assert result.tone == "formal"
        assert result.execution_mode == "auto"

    def test_creates_defaults_when_no_history(self):
        """When no preferences exist, returns defaults."""
        user_id = _make_user_id()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        async def mock_refresh(obj):
            obj.tone = "casual"
            obj.working_hours_start = time(9, 0)
            obj.working_hours_end = time(18, 0)
            obj.working_days = [1, 2, 3, 4, 5]
            obj.meeting_duration = 30
            obj.followup_threshold = 3
            obj.execution_mode = "suggest"

        session.refresh = mock_refresh

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.infer_preferences_from_history(user_id))

        assert result.tone == "casual"
        assert result.execution_mode == "suggest"

    def test_returns_user_preferences_type(self):
        """Return type is always UserPreferences."""
        user_id = _make_user_id()

        pref_row = _make_pref_mock()

        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pref_row
        session.execute.return_value = mock_result

        engine = BehaviorEngine(session)
        result = asyncio.run(engine.infer_preferences_from_history(user_id))

        assert isinstance(result, UserPreferences)
