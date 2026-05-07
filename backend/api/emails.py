"""
Emails API router — email fetch, classify, and reply endpoints.

Routes:
    GET  /emails                    → fetch + classify emails (Req 3.1–3.4)
    GET  /emails/{email_id}         → fetch single email
    POST /emails/generate-reply     → generate AI reply draft (rate-limited 30/min, Req 4.1–4.5, 12.4)
    POST /emails/{email_id}/send-reply  → send an existing reply draft (Req 4.5)
    POST /emails/{email_id}/embed   → embed email into FAISS (Req 5.1–5.4)

Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 12.4
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user, get_db
from backend.schemas.pydantic_schemas import (
    EmailMessage,
    GenerateReplyRequest,
    ReplyDraft,
    User,
)
from backend.services.analytics_service import AnalyticsService
from backend.services.behavior_engine import BehaviorEngine
from backend.services.decision_engine import DecisionEngine
from backend.services.email_service import EmailService
from backend.utils.faiss_store import FAISSStore

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Rate limiter — imported from backend.utils.rate_limit to avoid a circular
# dependency with backend.main (which imports this module).
# ---------------------------------------------------------------------------

from backend.utils.rate_limit import limiter


# ---------------------------------------------------------------------------
# Service factory helpers
# ---------------------------------------------------------------------------


def _make_email_service(session: AsyncSession) -> EmailService:
    """
    Instantiate EmailService with all required dependencies.

    Uses environment variables for OpenAI API key.  FAISSStore defaults to
    the ./faiss_indexes/ directory.
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

    return EmailService(
        session=session,
        faiss_store=faiss_store,
        openai_client=openai_sync_client,
        decision_engine=decision_engine,
        behavior_engine=behavior_engine,
        analytics_service=analytics_service,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[EmailMessage],
    summary="Fetch and classify emails",
)
async def list_emails(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EmailMessage]:
    """
    Fetch emails from Gmail and classify each one.

    Steps:
    1. Fetch up to 20 emails from Gmail (falls back to mock data on error).
    2. Classify each email (urgent/normal/low + category).
    3. Persist classification to the emails table.
    4. Log token usage to analytics.

    Returns the list of classified EmailMessage objects.

    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    user_id = str(current_user.id)
    email_service = _make_email_service(db)

    emails = await email_service.fetch_emails(user_id)
    classified = await email_service.classify_emails(user_id, emails)

    logger.info(
        "GET /emails — user=%s, fetched=%d, classified=%d",
        user_id,
        len(emails),
        len(classified),
    )
    return classified


@router.get(
    "/{email_id}",
    response_model=EmailMessage,
    summary="Fetch a single email by ID",
)
async def get_email(
    email_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailMessage:
    """
    Return a single EmailMessage by its UUID.

    Raises HTTP 404 if the email does not exist or does not belong to the
    authenticated user.

    Requirements: 4.3
    """
    user_id = str(current_user.id)
    email_service = _make_email_service(db)

    email = await email_service.get_email(user_id, str(email_id))

    logger.info("GET /emails/%s — user=%s", email_id, user_id)
    return email


@router.post(
    "/generate-reply",
    response_model=ReplyDraft,
    summary="Generate an AI reply draft (rate-limited: 30 req/min)",
)
@limiter.limit("30/minute")
async def generate_reply(
    request: Request,
    body: GenerateReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReplyDraft:
    """
    Generate an AI reply draft for the specified email.

    - Queries FAISS for up to 5 similar past emails to inform tone/style (Req 4.2).
    - Persists the draft with status="pending" (Req 4.3).
    - In suggest/approval mode the draft is NOT sent (Req 4.4).
    - In auto mode the draft is sent immediately (Req 4.5).
    - Rate-limited to 30 requests per minute per IP (Req 12.4).

    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 12.4
    """
    user_id = str(current_user.id)
    email_service = _make_email_service(db)

    draft = await email_service.generate_reply_draft(user_id, str(body.email_id))

    logger.info(
        "POST /emails/generate-reply — user=%s, email_id=%s, draft_id=%s, status=%s",
        user_id,
        body.email_id,
        draft.id,
        draft.status,
    )
    return draft


@router.post(
    "/{email_id}/send-reply",
    summary="Send an existing reply draft",
)
async def send_reply(
    email_id: UUID,
    draft_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send a previously generated reply draft via Gmail.

    The ``draft_id`` query parameter identifies which draft to send.
    Returns ``{"success": true, "message_id": "<gmail_id>"}`` on success.

    Raises HTTP 403 if the user's execution mode is not "auto".
    Raises HTTP 404 if the draft is not found.

    Requirements: 4.5
    """
    user_id = str(current_user.id)
    email_service = _make_email_service(db)

    result = await email_service.send_reply(user_id, str(draft_id))

    logger.info(
        "POST /emails/%s/send-reply — user=%s, draft_id=%s, success=%s",
        email_id,
        user_id,
        draft_id,
        result.get("success"),
    )
    return dict(result)


@router.post(
    "/{email_id}/embed",
    status_code=200,
    summary="Embed an email into the FAISS vector store",
)
async def embed_email(
    email_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generate a 1536-dim embedding for the email and upsert it into FAISS.

    Fetches the email from the database, generates an OpenAI embedding, and
    stores it in the user's FAISS index so it can be retrieved as a similar
    email during future reply generation.

    Returns ``{"status": "ok"}`` on success.

    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    user_id = str(current_user.id)
    email_service = _make_email_service(db)

    # Fetch the email first so we have the full EmailMessage object
    email = await email_service.get_email(user_id, str(email_id))

    await email_service.embed_and_store(user_id, email)

    logger.info(
        "POST /emails/%s/embed — user=%s, embedded successfully",
        email_id,
        user_id,
    )
    return {"status": "ok"}
