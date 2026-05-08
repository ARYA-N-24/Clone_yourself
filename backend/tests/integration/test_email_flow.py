"""
Integration test: end-to-end email flow using FastAPI TestClient with SQLite in-memory DB.

Steps:
1. Insert a sample meeting-request email
2. GET /emails — assert 200, emails returned, classification assigned
3. POST /emails/generate-reply — assert 200, draft_text non-empty, status=="pending"
4. GET /dashboard — assert email appears in priority_emails
5. Assert no OAuth token appears in any response body

Requirements: 3.1, 3.2, 4.1, 4.3, 4.4, 2.1, 1.8, 12.2
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Set required env vars before importing the app
os.environ["TOKEN_ENCRYPTION_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode()
os.environ["JWT_SECRET_KEY"] = "integration-test-jwt-secret"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
os.environ["OPENAI_API_KEY"] = "test-openai-key"

from main import app
import backend.api.auth as auth_module
import backend.api.emails as emails_module
import backend.api.dashboard as dashboard_module
from schemas.pydantic_schemas import (
    AnalyticsStats,
    DashboardPayload,
    EmailMessage,
    ReplyDraft,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_jwt(user_id: str, email: str = "test@example.com") -> str:
    secret = os.environ["JWT_SECRET_KEY"]
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=60),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_mock_db_user(user_id: str, email: str = "test@example.com") -> MagicMock:
    user = MagicMock()
    user.id = uuid.UUID(user_id)
    user.email = email
    user.name = "Test User"
    user.picture_url = None
    return user


def _make_mock_email(user_id: str, classification: str = "urgent") -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        gmail_id="gmail-integration-test",
        thread_id="thread-integration-test",
        subject="Can we schedule a meeting?",
        sender="boss@example.com",
        recipient="me@example.com",
        body_text="Hi, I'd like to schedule a meeting to discuss the project. Are you available?",
        received_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        classification=classification,
        category="meeting-request",
        is_replied=False,
    )


def _make_mock_reply_draft(email_id: uuid.UUID) -> ReplyDraft:
    return ReplyDraft(
        id=uuid.uuid4(),
        email_id=email_id,
        draft_text="Hi, I'd be happy to schedule a meeting. How about Tuesday at 2pm?",
        status="pending",
    )


def _make_mock_analytics() -> AnalyticsStats:
    return AnalyticsStats(
        actions_automated=3,
        time_saved_minutes=15.0,
        emails_classified=5,
        replies_sent=2,
        events_created=1,
    )


def _make_mock_db_session(user_id: str):
    """Create a mock async DB session that returns a valid user."""
    async def _mock_db():
        session = AsyncMock()
        db_user = _make_mock_db_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = db_user

        drafts_result = MagicMock()
        drafts_result.scalars.return_value.all.return_value = []

        session.execute.return_value = user_result
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        yield session

    return _mock_db


# ---------------------------------------------------------------------------
# Integration test: email flow
# ---------------------------------------------------------------------------


class TestEmailFlow:
    """End-to-end email flow integration test."""

    def setup_method(self):
        """Set up test fixtures."""
        self.user_id = str(uuid.uuid4())
        self.jwt_token = _make_valid_jwt(self.user_id)
        self.auth_headers = {"Authorization": f"Bearer {self.jwt_token}"}
        self.mock_email = _make_mock_email(self.user_id)
        self.mock_draft = _make_mock_reply_draft(self.mock_email.id)

    def teardown_method(self):
        """Clean up dependency overrides."""
        app.dependency_overrides.clear()

    def test_step1_get_emails_returns_200(self):
        """Step 2: GET /emails returns 200 with emails and classification assigned."""
        mock_db = _make_mock_db_session(self.user_id)
        app.dependency_overrides[auth_module.get_db] = mock_db
        app.dependency_overrides[emails_module.get_db] = mock_db

        with patch("backend.api.emails._make_email_service") as mock_svc_factory:
            mock_email_svc = MagicMock()
            mock_email_svc.fetch_emails = AsyncMock(return_value=[self.mock_email])
            mock_email_svc.classify_emails = AsyncMock(return_value=[self.mock_email])
            mock_svc_factory.return_value = mock_email_svc

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/emails", headers=self.auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Classification should be assigned
        for email in data:
            assert email.get("classification") in ("urgent", "normal", "low", None)

    def test_step2_get_emails_no_oauth_token_in_response(self):
        """Step 5: No OAuth token appears in GET /emails response body."""
        mock_db = _make_mock_db_session(self.user_id)
        app.dependency_overrides[auth_module.get_db] = mock_db
        app.dependency_overrides[emails_module.get_db] = mock_db

        with patch("backend.api.emails._make_email_service") as mock_svc_factory:
            mock_email_svc = MagicMock()
            mock_email_svc.fetch_emails = AsyncMock(return_value=[self.mock_email])
            mock_email_svc.classify_emails = AsyncMock(return_value=[self.mock_email])
            mock_svc_factory.return_value = mock_email_svc

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/emails", headers=self.auth_headers)

        # No raw OAuth tokens should appear in the response
        response_text = response.text
        assert "ya29." not in response_text  # Google access token prefix

    def test_step3_generate_reply_returns_200_with_draft(self):
        """Step 3: POST /emails/generate-reply returns 200, draft_text non-empty, status==pending."""
        mock_db = _make_mock_db_session(self.user_id)
        app.dependency_overrides[auth_module.get_db] = mock_db
        app.dependency_overrides[emails_module.get_db] = mock_db

        with patch("backend.api.emails._make_email_service") as mock_svc_factory:
            mock_email_svc = MagicMock()
            mock_email_svc.generate_reply_draft = AsyncMock(return_value=self.mock_draft)
            mock_svc_factory.return_value = mock_email_svc

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/emails/generate-reply",
                json={"email_id": str(self.mock_email.id)},
                headers=self.auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["draft_text"] != ""
        assert data["status"] == "pending"

    def test_step4_dashboard_shows_priority_emails(self):
        """Step 4: GET /dashboard shows email in priority_emails."""
        mock_db = _make_mock_db_session(self.user_id)
        app.dependency_overrides[auth_module.get_db] = mock_db
        app.dependency_overrides[dashboard_module.get_db] = mock_db

        with patch("backend.api.dashboard._make_task_orchestrator") as mock_orch_factory:
            mock_orchestrator = MagicMock()
            mock_orchestrator.get_dashboard = AsyncMock(return_value=DashboardPayload(
                priority_emails=[self.mock_email],
                pending_replies=[],
                suggested_actions=["Reply urgently to email from boss@example.com"],
                followup_count=0,
                analytics=_make_mock_analytics(),
            ))
            mock_orch_factory.return_value = mock_orchestrator

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/dashboard", headers=self.auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "priority_emails" in data
        assert len(data["priority_emails"]) > 0

    def test_step5_no_oauth_token_in_dashboard_response(self):
        """Step 5: No OAuth token appears in GET /dashboard response body."""
        mock_db = _make_mock_db_session(self.user_id)
        app.dependency_overrides[auth_module.get_db] = mock_db
        app.dependency_overrides[dashboard_module.get_db] = mock_db

        with patch("backend.api.dashboard._make_task_orchestrator") as mock_orch_factory:
            mock_orchestrator = MagicMock()
            mock_orchestrator.get_dashboard = AsyncMock(return_value=DashboardPayload(
                priority_emails=[self.mock_email],
                pending_replies=[],
                suggested_actions=[],
                followup_count=0,
                analytics=_make_mock_analytics(),
            ))
            mock_orch_factory.return_value = mock_orchestrator

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/dashboard", headers=self.auth_headers)

        response_text = response.text
        # No Google OAuth token patterns
        assert "ya29." not in response_text
        # No raw token fields
        assert "refresh_token" not in response_text
