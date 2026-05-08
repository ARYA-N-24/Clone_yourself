"""
Auth API router — Google OAuth 2.0 endpoints.

Routes:
    GET  /auth/google    → redirect to Google OAuth consent screen
    GET  /auth/callback  → exchange code, encrypt tokens, issue JWT
    POST /auth/refresh   → validate JWT, auto-refresh Google token if expired, return new JWT
    POST /auth/revoke    → invalidate stored tokens, terminate session

Security:
    - OAuth tokens are AES-256 encrypted before DB storage (Req 1.3, 12.1)
    - OAuth tokens are NEVER included in any API response body (Req 1.8, 12.2)
    - JWT is validated on every protected request (Req 1.4)
    - Expired access tokens are auto-refreshed before retrying (Req 1.5)
    - Revoked tokens return HTTP 401 {"error": "reauth_required"} (Req 1.6)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import google.auth.transport.requests
import google.oauth2.credentials
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google_auth_oauthlib.flow import Flow
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.db_models import OAuthToken, User
from schemas.pydantic_schemas import TokenResponse
from schemas.pydantic_schemas import User as UserSchema
from utils.token_encryption import decrypt_token, encrypt_token

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_MINUTES = 60


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        raise EnvironmentError("JWT_SECRET_KEY environment variable is not set.")
    return secret


def _google_client_id() -> str:
    val = os.environ.get("GOOGLE_CLIENT_ID", "")
    if not val:
        raise EnvironmentError("GOOGLE_CLIENT_ID environment variable is not set.")
    return val


def _google_client_secret() -> str:
    val = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not val:
        raise EnvironmentError("GOOGLE_CLIENT_SECRET environment variable is not set.")
    return val


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _redirect_uri() -> str:
    """Callback URL that Google will redirect to after consent."""
    # The callback is served by this backend, not the frontend
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    print("============================backend uri rediret ==============", backend_url)
    return f"{backend_url}/auth/callback"


# ---------------------------------------------------------------------------
# Database session dependency
# ---------------------------------------------------------------------------

def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise EnvironmentError("DATABASE_URL environment variable is not set.")
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(_get_database_url(), echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields an AsyncSession."""
    factory = _make_session_factory()
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_jwt(user_id: str, email: str) -> str:
    """Issue a signed JWT containing user_id and email."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=_JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict:
    """
    Decode and validate a JWT.

    Raises:
        HTTPException 401 if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    """
    FastAPI dependency that validates the Bearer JWT and returns the User.

    - Extracts Bearer token from Authorization header
    - Decodes and validates JWT signature and expiry
    - Looks up user in DB
    - Returns User Pydantic model (never the token itself)
    - Returns 401 if invalid/expired/user not found

    Requirements: 1.4, 1.8, 12.2
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_token"},
        )

    payload = _decode_jwt(credentials.credentials)

    user_id_str: Optional[str] = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token"},
        )

    try:
        user_uuid = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token"},
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    db_user = result.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "user_not_found"},
        )

    # Return Pydantic schema — never the raw token
    return UserSchema.model_validate(db_user)


# ---------------------------------------------------------------------------
# OAuth Flow factory
# ---------------------------------------------------------------------------

def _build_flow() -> Flow:
    """Construct a google-auth-oauthlib Flow from environment credentials."""
    client_config = {
        "web": {
            "client_id": _google_client_id(),
            "client_secret": _google_client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=_GOOGLE_SCOPES,
        redirect_uri=_redirect_uri(),
    )
    return flow


# ---------------------------------------------------------------------------
# Route: GET /auth/google
# ---------------------------------------------------------------------------

@router.get("/google", summary="Redirect to Google OAuth consent screen")
async def google_oauth_redirect() -> RedirectResponse:
    """
    Redirect the user to the Google OAuth 2.0 consent screen.

    Scopes requested: gmail.readonly, gmail.send, calendar.readonly,
    calendar.events (plus openid and profile for user info).

    Requirements: 1.1, 12.6
    """
    flow = _build_flow()
    authorization_url, _state = flow.authorization_url(
        access_type="offline",   # request refresh token
        include_granted_scopes="true",
        prompt="consent",        # force consent to always get refresh token
    )
    return RedirectResponse(url=authorization_url)


# ---------------------------------------------------------------------------
# Route: GET /auth/callback
# ---------------------------------------------------------------------------

class NextAuthRequest(BaseModel):
    email: str
    name: str
    picture_url: Optional[str] = None
    access_token: str
    refresh_token: str
    expires_at: Optional[int] = None

@router.post("/nextauth", summary="Sync NextAuth tokens and get backend JWT")
async def nextauth_sync(
    body: NextAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Receive Google tokens from NextAuth, upsert the user, encrypt and store
    the tokens, and issue a backend JWT.
    """
    # Upsert user
    result = await db.execute(select(User).where(User.email == body.email))
    db_user = result.scalar_one_or_none()

    if db_user is None:
        db_user = User(email=body.email, name=body.name, picture_url=body.picture_url)
        db.add(db_user)
        await db.flush()  # populate db_user.id
    else:
        db_user.name = body.name
        if body.picture_url:
            db_user.picture_url = body.picture_url

    # Encrypt tokens before storing
    encrypted_access = encrypt_token(body.access_token)
    encrypted_refresh = encrypt_token(body.refresh_token) if body.refresh_token else encrypt_token("")

    token_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    if body.expires_at:
        token_expiry = datetime.fromtimestamp(body.expires_at, tz=timezone.utc)

    # Upsert oauth_tokens
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.user_id == db_user.id)
    )
    db_token = token_result.scalar_one_or_none()

    if db_token is None:
        db_token = OAuthToken(
            user_id=db_user.id,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=token_expiry,
            scopes=_GOOGLE_SCOPES,
        )
        db.add(db_token)
    else:
        db_token.access_token = encrypted_access
        # Only update refresh token if a new one is provided by NextAuth
        if body.refresh_token:
            db_token.refresh_token = encrypted_refresh
        db_token.token_expiry = token_expiry
        db_token.scopes = _GOOGLE_SCOPES
        db_token.updated_at = datetime.now(tz=timezone.utc)

    await db.commit()

    # Issue backend JWT
    jwt_token = _create_jwt(str(db_user.id), db_user.email)
    return TokenResponse(access_token=jwt_token)


@router.get("/callback", summary="Handle Google OAuth callback")
async def google_oauth_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange the authorization code for Google OAuth tokens, encrypt and
    store them, create/update the user record, and issue a JWT.

    The response contains ONLY the JWT — no raw OAuth tokens are returned.

    Requirements: 1.2, 1.3, 1.8, 12.2
    """
    flow = _build_flow()

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "token_exchange_failed", "message": str(exc)},
        ) from exc

    credentials = flow.credentials

    # Fetch user info from Google
    import httpx  # local import to keep top-level imports clean

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail={"error": "userinfo_fetch_failed"},
            )
        user_info = resp.json()

    email: str = user_info.get("email", "")
    name: str = user_info.get("name", email)
    picture_url: Optional[str] = user_info.get("picture")

    if not email:
        raise HTTPException(
            status_code=502,
            detail={"error": "userinfo_missing_email"},
        )

    # Upsert user in the users table
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()

    if db_user is None:
        db_user = User(email=email, name=name, picture_url=picture_url)
        db.add(db_user)
        await db.flush()  # populate db_user.id
    else:
        db_user.name = name
        if picture_url:
            db_user.picture_url = picture_url

    # Encrypt tokens before storing (Req 1.3, 12.1)
    encrypted_access = encrypt_token(credentials.token)
    encrypted_refresh = encrypt_token(credentials.refresh_token or "")

    token_expiry: datetime = (
        credentials.expiry
        if credentials.expiry is not None
        else datetime.now(tz=timezone.utc) + timedelta(hours=1)
    )
    # Ensure timezone-aware
    if token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    scopes: list[str] = list(credentials.scopes or _GOOGLE_SCOPES)

    # Upsert oauth_tokens row for this user
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.user_id == db_user.id)
    )
    db_token = token_result.scalar_one_or_none()

    if db_token is None:
        db_token = OAuthToken(
            user_id=db_user.id,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=token_expiry,
            scopes=scopes,
        )
        db.add(db_token)
    else:
        db_token.access_token = encrypted_access
        db_token.refresh_token = encrypted_refresh
        db_token.token_expiry = token_expiry
        db_token.scopes = scopes
        db_token.updated_at = datetime.now(tz=timezone.utc)

    await db.commit()

    # Issue JWT — contains only user_id and email, never OAuth tokens
    jwt_token = _create_jwt(str(db_user.id), db_user.email)

    # TokenResponse contains only the JWT (Req 1.8, 12.2)
    return TokenResponse(access_token=jwt_token)


# ---------------------------------------------------------------------------
# Route: POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", summary="Refresh JWT; auto-refresh Google token if expired")
async def refresh_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Accept a JWT in the Authorization header.

    1. Validate the JWT (signature + expiry).
    2. Look up the user's stored Google OAuth token.
    3. If the Google access token has expired, auto-refresh it using the
       stored refresh token and persist the new encrypted tokens.
    4. Return a fresh JWT.

    If the Google token refresh fails (revoked), return HTTP 401
    {"error": "reauth_required"}.

    Requirements: 1.4, 1.5, 1.6, 1.8, 12.2
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_token"},
        )

    payload = _decode_jwt(credentials.credentials)

    user_id_str: Optional[str] = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    try:
        user_uuid = UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_uuid))
    db_user = user_result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=401, detail={"error": "user_not_found"})

    # Load stored OAuth token
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.user_id == user_uuid)
    )
    db_token = token_result.scalar_one_or_none()
    if db_token is None:
        raise HTTPException(status_code=401, detail={"error": "reauth_required"})

    # Auto-refresh Google access token if expired (Req 1.5)
    now = datetime.now(tz=timezone.utc)
    token_expiry = db_token.token_expiry
    if token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    if now >= token_expiry:
        # Attempt to refresh using stored refresh token
        try:
            refresh_token_plain = decrypt_token(db_token.refresh_token)
        except (ValueError, EnvironmentError):
            raise HTTPException(
                status_code=401, detail={"error": "reauth_required"}
            )

        if not refresh_token_plain:
            raise HTTPException(
                status_code=401, detail={"error": "reauth_required"}
            )

        google_creds = google.oauth2.credentials.Credentials(
            token=None,
            refresh_token=refresh_token_plain,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=_google_client_id(),
            client_secret=_google_client_secret(),
            scopes=db_token.scopes,
        )

        try:
            request = google.auth.transport.requests.Request()
            google_creds.refresh(request)
        except Exception:
            # Refresh failed — token revoked or invalid (Req 1.6)
            raise HTTPException(
                status_code=401, detail={"error": "reauth_required"}
            )

        # Persist updated encrypted tokens
        new_expiry: datetime = (
            google_creds.expiry
            if google_creds.expiry is not None
            else now + timedelta(hours=1)
        )
        if new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)

        db_token.access_token = encrypt_token(google_creds.token)
        db_token.refresh_token = encrypt_token(google_creds.refresh_token or refresh_token_plain)
        db_token.token_expiry = new_expiry
        db_token.updated_at = now
        await db.commit()

    # Issue a fresh JWT — never include OAuth tokens in response (Req 1.8, 12.2)
    new_jwt = _create_jwt(str(db_user.id), db_user.email)
    return TokenResponse(access_token=new_jwt)


# ---------------------------------------------------------------------------
# Route: POST /auth/revoke
# ---------------------------------------------------------------------------

@router.post("/revoke", summary="Revoke session and invalidate stored tokens")
async def revoke_token(
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Invalidate the user's stored OAuth tokens and terminate the session.

    Deletes the oauth_tokens row for the authenticated user so that
    subsequent requests will require re-authentication.

    Requirements: 1.7
    """
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.user_id == current_user.id)
    )
    db_token = token_result.scalar_one_or_none()

    if db_token is not None:
        await db.delete(db_token)
        await db.commit()

    return {"status": "revoked"}
