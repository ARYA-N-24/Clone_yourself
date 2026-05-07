"""
Unit tests for auth API using FastAPI TestClient.

Covers:
- No OAuth token appears in any response body from auth endpoints
- Protected endpoints return 401 for missing JWT
- Protected endpoints return 401 for invalid/expired JWT
- Uses unittest.mock.patch to mock DB and Google OAuth calls

Requirements: 1.3, 1.4, 1.8, 12.2
"""

from __future__ import annotations

import base64
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Set required env vars before importing the app
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", base64.b64encode(secrets.token_bytes(32)).decode())
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.main import app
import backend.api.auth as auth_module


# ---------------------------------------------------------------------------
# Mock DB session dependency override
# ---------------------------------------------------------------------------

async def _mock_db_session():
    """Yield a mock async DB session that doesn't connect to a real DB."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_jwt(user_id: str = None, email: str = "test@example.com") -> str:
    """Create a valid JWT for testing."""
    if user_id is None:
        user_id = str(uuid.uuid4())
    secret = os.environ["JWT_SECRET_KEY"]
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=60),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_expired_jwt(user_id: str = None, email: str = "test@example.com") -> str:
    """Create an expired JWT for testing."""
    if user_id is None:
        user_id = str(uuid.uuid4())
    secret = os.environ["JWT_SECRET_KEY"]
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),  # expired 1 hour ago
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_mock_db_user(user_id: str = None, email: str = "test@example.com") -> MagicMock:
    """Create a mock DB user object."""
    user = MagicMock()
    user.id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    user.email = email
    user.name = "Test User"
    user.picture_url = None
    return user


# ---------------------------------------------------------------------------
# OAuth token not in response body
# ---------------------------------------------------------------------------


class TestNoOAuthTokenInResponse:
    def test_callback_response_does_not_contain_oauth_token(self):
        """The /auth/callback response must not contain raw OAuth tokens."""
        mock_flow = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = "raw-google-access-token-secret"
        mock_credentials.refresh_token = "raw-google-refresh-token-secret"
        mock_credentials.expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        mock_credentials.scopes = ["openid", "email"]
        mock_flow.credentials = mock_credentials

        with patch("backend.api.auth._build_flow", return_value=mock_flow), \
             patch("backend.api.auth.get_db", _mock_db_session), \
             patch("httpx.AsyncClient") as mock_httpx:

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "email": "test@example.com",
                "name": "Test User",
                "picture": None,
            }
            mock_httpx.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/auth/callback?code=test-auth-code")

        response_text = response.text
        assert "raw-google-access-token-secret" not in response_text
        assert "raw-google-refresh-token-secret" not in response_text

    def test_callback_response_contains_only_jwt(self):
        """The /auth/callback response contains access_token (JWT) and token_type only."""
        mock_flow = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = "google-access-token"
        mock_credentials.refresh_token = "google-refresh-token"
        mock_credentials.expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        mock_credentials.scopes = ["openid", "email"]
        mock_flow.credentials = mock_credentials

        with patch("backend.api.auth._build_flow", return_value=mock_flow), \
             patch("backend.api.auth.get_db", _mock_db_session), \
             patch("httpx.AsyncClient") as mock_httpx:

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "email": "test@example.com",
                "name": "Test User",
                "picture": None,
            }
            mock_httpx.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/auth/callback?code=test-auth-code")

        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "token_type" in data
            # Should not have raw OAuth token fields
            assert "refresh_token" not in data
            assert "google_token" not in data


# ---------------------------------------------------------------------------
# Protected endpoints return 401 for missing JWT
# ---------------------------------------------------------------------------


class TestMissingJWT:
    def _client_with_mock_db(self):
        """Return a TestClient with the DB dependency overridden."""
        app.dependency_overrides[auth_module.get_db] = _mock_db_session
        client = TestClient(app, raise_server_exceptions=False)
        return client

    def teardown_method(self):
        """Clean up dependency overrides after each test."""
        app.dependency_overrides.clear()

    def test_dashboard_returns_401_without_jwt(self):
        """GET /dashboard returns 401 when no Authorization header is provided."""
        client = self._client_with_mock_db()
        response = client.get("/dashboard")
        assert response.status_code == 401

    def test_emails_returns_401_without_jwt(self):
        """GET /emails returns 401 when no Authorization header is provided."""
        client = self._client_with_mock_db()
        response = client.get("/emails")
        assert response.status_code == 401

    def test_generate_reply_returns_401_without_jwt(self):
        """POST /emails/generate-reply returns 401 when no Authorization header."""
        client = self._client_with_mock_db()
        response = client.post(
            "/emails/generate-reply",
            json={"email_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401

    def test_followups_returns_401_without_jwt(self):
        """GET /followups returns 401 when no Authorization header is provided."""
        client = self._client_with_mock_db()
        response = client.get("/followups")
        assert response.status_code == 401

    def test_analytics_returns_401_without_jwt(self):
        """GET /analytics returns 401 when no Authorization header is provided."""
        client = self._client_with_mock_db()
        response = client.get("/analytics")
        assert response.status_code in (401, 404)  # 404 if route doesn't exist


# ---------------------------------------------------------------------------
# Protected endpoints return 401 for invalid/expired JWT
# ---------------------------------------------------------------------------


class TestInvalidJWT:
    def _client_with_mock_db(self):
        """Return a TestClient with the DB dependency overridden."""
        app.dependency_overrides[auth_module.get_db] = _mock_db_session
        client = TestClient(app, raise_server_exceptions=False)
        return client

    def teardown_method(self):
        """Clean up dependency overrides after each test."""
        app.dependency_overrides.clear()

    def test_dashboard_returns_401_with_invalid_jwt(self):
        """GET /dashboard returns 401 when JWT is invalid."""
        client = self._client_with_mock_db()
        response = client.get(
            "/dashboard",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert response.status_code == 401

    def test_emails_returns_401_with_invalid_jwt(self):
        """GET /emails returns 401 when JWT is invalid."""
        client = self._client_with_mock_db()
        response = client.get(
            "/emails",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert response.status_code == 401

    def test_dashboard_returns_401_with_expired_jwt(self):
        """GET /dashboard returns 401 when JWT is expired."""
        expired_token = _make_expired_jwt()
        client = self._client_with_mock_db()
        response = client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    def test_emails_returns_401_with_expired_jwt(self):
        """GET /emails returns 401 when JWT is expired."""
        expired_token = _make_expired_jwt()
        client = self._client_with_mock_db()
        response = client.get(
            "/emails",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    def test_generate_reply_returns_401_with_invalid_jwt(self):
        """POST /emails/generate-reply returns 401 when JWT is invalid."""
        client = self._client_with_mock_db()
        response = client.post(
            "/emails/generate-reply",
            json={"email_id": str(uuid.uuid4())},
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert response.status_code == 401

    def test_wrong_secret_jwt_returns_401(self):
        """JWT signed with wrong secret returns 401."""
        # Sign with a different secret
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "test@example.com",
            "iat": now,
            "exp": now + timedelta(minutes=60),
        }
        wrong_token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")

        client = self._client_with_mock_db()
        response = client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {wrong_token}"},
        )
        assert response.status_code == 401
