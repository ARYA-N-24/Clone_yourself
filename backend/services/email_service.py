"""
Email Service for the Clone Yourself Platform.

Fetches emails from Gmail API, stores them in PostgreSQL, and coordinates
classification, reply generation, and embedding.

Interface:
    - fetch_emails(user_id, max_results) → list[EmailMessage]
    - get_email(user_id, email_id) → EmailMessage
    - classify_emails(user_id, emails) → list[ClassifiedEmail]
    - generate_reply_draft(user_id, email_id) → ReplyDraft
    - send_reply(user_id, draft_id) → SendResult
    - embed_and_store(user_id, email) → None

Requirements: 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 13.2
"""

from __future__ import annotations

import base64
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import TypedDict
from uuid import UUID

import openai
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.db_models import AnalyticsEvent as AnalyticsEventORM
from backend.models.db_models import Email as EmailORM
from backend.models.db_models import OAuthToken, ReplyDraft as ReplyDraftORM
from backend.models.db_models import UserPreference
from backend.schemas.pydantic_schemas import (
    AnalyticsEvent,
    EmailMessage,
    ReplyDraft,
    StyleContext,
)
from backend.services.analytics_service import AnalyticsService
from backend.services.behavior_engine import BehaviorEngine
from backend.services.decision_engine import DecisionEngine
from backend.utils.faiss_store import FAISSStore
from backend.utils.token_encryption import decrypt_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SendResult(TypedDict):
    """Result of a send_reply operation."""

    success: bool
    message_id: str | None


# ClassifiedEmail is the same type as EmailMessage — classification field is populated.
ClassifiedEmail = EmailMessage


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------


class EmailService:
    """
    Fetches, classifies, and replies to emails via Gmail API.

    Args:
        session: SQLAlchemy AsyncSession for database operations.
        faiss_store: FAISSStore instance for email embeddings.
        openai_client: openai.OpenAI (sync) client for embeddings.
        decision_engine: DecisionEngine for classification and reply generation.
        behavior_engine: BehaviorEngine for writing style context.
        analytics_service: AnalyticsService for recording events.
    """

    def __init__(
        self,
        session: AsyncSession,
        faiss_store: FAISSStore,
        openai_client: openai.OpenAI,
        decision_engine: DecisionEngine,
        behavior_engine: BehaviorEngine,
        analytics_service: AnalyticsService,
    ) -> None:
        self._session = session
        self._faiss = faiss_store
        self._openai = openai_client
        self._decision = decision_engine
        self._behavior = behavior_engine
        self._analytics = analytics_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_oauth_token(self, user_id: str) -> tuple[str, str]:
        """
        Retrieve and decrypt the user's OAuth access and refresh tokens.

        Args:
            user_id: UUID string of the user.

        Returns:
            Tuple of (access_token, refresh_token) as plaintext strings.

        Raises:
            HTTPException(401): If no OAuth token is found for the user.
        """
        user_uuid = UUID(user_id)
        stmt = (
            select(OAuthToken)
            .where(OAuthToken.user_id == user_uuid)
            .order_by(OAuthToken.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        token_row = result.scalar_one_or_none()

        if token_row is None:
            raise HTTPException(status_code=401, detail="No OAuth token found for user.")

        access_token = decrypt_token(token_row.access_token)
        refresh_token = decrypt_token(token_row.refresh_token)
        return access_token, refresh_token

    def _build_gmail_client(self, access_token: str, refresh_token: str):
        """
        Build a Gmail API client using the user's OAuth credentials.

        Args:
            access_token: Decrypted OAuth access token.
            refresh_token: Decrypted OAuth refresh token.

        Returns:
            A Google API client resource for the Gmail v1 API.
        """
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @staticmethod
    def _parse_gmail_message(raw_msg: dict, user_id: str) -> EmailMessage:
        """
        Parse a raw Gmail API message dict into an EmailMessage Pydantic model.

        Args:
            raw_msg: Raw message dict from Gmail API (with 'payload' and 'id').
            user_id: UUID string of the user (used as recipient fallback).

        Returns:
            EmailMessage populated from the raw Gmail message.
        """
        msg_id = raw_msg.get("id", "")
        thread_id = raw_msg.get("threadId", "")

        # Extract headers
        headers: dict[str, str] = {}
        payload = raw_msg.get("payload", {})
        for header in payload.get("headers", []):
            name = header.get("name", "").lower()
            value = header.get("value", "")
            headers[name] = value

        subject = headers.get("subject")
        sender = headers.get("from", "unknown@unknown.com")
        recipient = headers.get("to", user_id)

        # Parse received_at from internalDate (milliseconds since epoch)
        internal_date_ms = int(raw_msg.get("internalDate", 0))
        received_at = datetime.fromtimestamp(
            internal_date_ms / 1000.0, tz=timezone.utc
        )

        # Extract body text
        body_text = _extract_body_text(payload)

        return EmailMessage(
            id=uuid.uuid4(),
            gmail_id=msg_id,
            thread_id=thread_id,
            subject=subject,
            sender=sender,
            recipient=recipient,
            body_text=body_text,
            received_at=received_at,
            classification=None,
            category=None,
            is_replied=False,
        )

    async def _upsert_email(self, user_id: str, email: EmailMessage) -> UUID:
        """
        Upsert an EmailMessage into the emails table.

        Uses PostgreSQL ON CONFLICT DO UPDATE to handle re-fetching the same email.

        Args:
            user_id: UUID string of the user.
            email: EmailMessage to upsert.
        """
        user_uuid = UUID(user_id)
        stmt = (
            pg_insert(EmailORM)
            .values(
                id=email.id,
                user_id=user_uuid,
                gmail_id=email.gmail_id,
                thread_id=email.thread_id,
                subject=email.subject,
                sender=email.sender,
                recipient=email.recipient,
                body_text=email.body_text,
                received_at=email.received_at,
                classification=email.classification,
                category=email.category,
                is_replied=email.is_replied,
            )
            .on_conflict_do_update(
                constraint="uq_emails_user_gmail",
                set_={
                    "subject": email.subject,
                    "body_text": email.body_text,
                    "classification": email.classification,
                    "category": email.category,
                    # Preserve is_replied=True if already set in DB
                    "is_replied": or_(EmailORM.is_replied, email.is_replied),
                },
            )
            .returning(EmailORM.id)
        )
        result = await self._session.execute(stmt)
        actual_id = result.scalar()
        await self._session.commit()
        return actual_id

    async def _get_execution_mode(self, user_id: str) -> str:
        """
        Retrieve the user's execution mode from user_preferences.

        Returns "suggest" as default if no preferences are found.

        Args:
            user_id: UUID string of the user.

        Returns:
            One of "suggest", "approval", or "auto".
        """
        user_uuid = UUID(user_id)
        stmt = select(UserPreference).where(UserPreference.user_id == user_uuid)
        result = await self._session.execute(stmt)
        pref_row = result.scalar_one_or_none()
        if pref_row is None:
            return "suggest"
        return pref_row.execution_mode

    # ------------------------------------------------------------------
    # fetch_emails
    # ------------------------------------------------------------------

    async def fetch_emails(
        self, user_id: str, max_results: int = 20
    ) -> list[EmailMessage]:
        """
        Fetch up to max_results emails from the user's Gmail inbox.

        Retrieves the user's OAuth token, builds a Gmail API client, and fetches
        messages. Falls back to MOCK_EMAILS on any Gmail API error (including 401).
        Upserts fetched emails into the emails table.

        Args:
            user_id: UUID string of the user.
            max_results: Maximum number of emails to fetch (default 20).

        Returns:
            List of EmailMessage objects.

        Requirements: 4.2, 4.3, 13.2
        """
        emails: list[EmailMessage] = []

        try:
            access_token, refresh_token = await self._get_oauth_token(user_id)
            gmail = self._build_gmail_client(access_token, refresh_token)

            # List message IDs from inbox
            list_req = (
                gmail.users()
                .messages()
                .list(userId="me", maxResults=max_results, labelIds=["INBOX"])
            )
            list_response = await asyncio.to_thread(list_req.execute)
            messages = list_response.get("messages", [])

            for msg_ref in messages:
                msg_id = msg_ref["id"]
                get_req = (
                    gmail.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                )
                raw_msg = await asyncio.to_thread(get_req.execute)
                email = self._parse_gmail_message(raw_msg, user_id)
                emails.append(email)

        except Exception as exc:
            logger.error(
                "Gmail API unavailable for user %s (%s); raising error instead of mock data.",
                user_id,
                exc,
            )
            raise HTTPException(status_code=503, detail="Gmail API is unavailable. Please check your Google OAuth connection.") from exc

        # Upsert all fetched emails into the database
        for email in emails:
            try:
                stable_id = await self._upsert_email(user_id, email)
                # Update the email object in the list with the stable ID from the DB
                email.id = stable_id
            except Exception as exc:
                logger.warning(
                    "Failed to upsert email %s for user %s: %s",
                    email.gmail_id,
                    user_id,
                    exc,
                )

        logger.info("Fetched %d emails for user %s.", len(emails), user_id)
        return emails

    # ------------------------------------------------------------------
    # get_email
    # ------------------------------------------------------------------

    async def get_email(self, user_id: str, email_id: str) -> EmailMessage:
        """
        Fetch a single email by ID from the database.

        Args:
            user_id: UUID string of the user.
            email_id: UUID string of the email.

        Returns:
            EmailMessage for the requested email.

        Raises:
            HTTPException(404): If the email is not found.

        Requirements: 4.3
        """
        user_uuid = UUID(user_id)
        email_uuid = UUID(email_id)

        stmt = select(EmailORM).where(
            EmailORM.id == email_uuid,
            EmailORM.user_id == user_uuid,
        )
        result = await self._session.execute(stmt)
        email_row = result.scalar_one_or_none()

        if email_row is None:
            raise HTTPException(status_code=404, detail="Email not found.")

        return EmailMessage.model_validate(email_row)

    # ------------------------------------------------------------------
    # classify_emails
    # ------------------------------------------------------------------

    async def classify_emails(
        self, user_id: str, emails: list[EmailMessage]
    ) -> list[ClassifiedEmail]:
        """
        Classify a list of emails using the DecisionEngine.

        For each email, calls DecisionEngine.classify_email(), updates the
        emails.classification and emails.category columns in the database,
        and records an email_classified analytics event.

        Args:
            user_id: UUID string of the user.
            emails: List of EmailMessage objects to classify.

        Returns:
            List of ClassifiedEmail (EmailMessage with classification populated).

        Requirements: 4.2, 4.3
        """
        user_prefs = await self._behavior.get_user_preferences(user_id)
        classified: list[ClassifiedEmail] = []

        for email in emails:
            try:
                classification = await self._decision.classify_email(email, user_prefs)
            except Exception as exc:
                logger.warning(
                    "Classification failed for email %s: %s; defaulting to 'normal'.",
                    email.id,
                    exc,
                )
                classification = "normal"

            # Build updated EmailMessage with classification
            classified_email = email.model_copy(
                update={"classification": classification}
            )

            # Update classification in the database
            try:
                stmt = select(EmailORM).where(EmailORM.id == email.id)
                result = await self._session.execute(stmt)
                email_row = result.scalar_one_or_none()
                if email_row is not None:
                    email_row.classification = classification
                    await self._session.commit()
            except Exception as exc:
                logger.warning(
                    "Failed to update classification for email %s: %s", email.id, exc
                )

            # Record analytics event
            try:
                event = AnalyticsEvent(
                    id=uuid.uuid4(),
                    user_id=UUID(user_id),
                    event_type="email_classified",
                    metadata_={"email_id": str(email.id), "classification": classification},
                    time_saved_min=0.0,
                    created_at=datetime.utcnow(),
                )
                await self._analytics.record_event(user_id, event)
            except Exception as exc:
                logger.warning(
                    "Failed to record analytics for email %s: %s", email.id, exc
                )

            classified.append(classified_email)

        logger.info(
            "Classified %d emails for user %s.", len(classified), user_id
        )
        return classified

    # ------------------------------------------------------------------
    # generate_reply_draft
    # ------------------------------------------------------------------

    async def generate_reply_draft(
        self, user_id: str, email_id: str
    ) -> ReplyDraft:
        """
        Generate an AI reply draft for the given email.

        Steps:
        1. Fetch the email from the database.
        2. Get writing style context from BehaviorEngine.
        3. Call DecisionEngine.generate_reply() to produce a draft.
        4. Persist the draft to reply_drafts table with status="pending".
        5. If execution mode is "auto", immediately call send_reply() and
           update status to "sent".

        Args:
            user_id: UUID string of the user.
            email_id: UUID string of the email to reply to.

        Returns:
            ReplyDraft with the generated draft text.

        Requirements: 4.4, 4.5
        """
        # Step 1: Fetch the email
        email = await self.get_email(user_id, email_id)

        # Step 2: Get writing style context
        style_ctx: StyleContext = await self._behavior.get_writing_style_context(
            user_id, email.body_text or ""
        )

        # Step 3: Generate reply via DecisionEngine
        draft: ReplyDraft = await self._decision.generate_reply(email, style_ctx)

        # Step 4: Persist draft to reply_drafts table
        user_uuid = UUID(user_id)
        draft_orm = ReplyDraftORM(
            id=draft.id,
            user_id=user_uuid,
            email_id=email.id,
            draft_text=draft.draft_text,
            status="pending",
        )
        self._session.add(draft_orm)
        await self._session.commit()
        await self._session.refresh(draft_orm)

        logger.info(
            "Generated reply draft %s for email %s (user %s).",
            draft.id,
            email_id,
            user_id,
        )

        # Step 5: Auto-send if execution mode is "auto"
        execution_mode = await self._get_execution_mode(user_id)
        if execution_mode == "auto":
            try:
                await self.send_reply(user_id, str(draft.id))
                draft = draft.model_copy(update={"status": "sent"})
            except Exception as exc:
                logger.warning(
                    "Auto-send failed for draft %s: %s", draft.id, exc
                )

        return draft

    # ------------------------------------------------------------------
    # create_manual_draft
    # ------------------------------------------------------------------

    async def create_manual_draft(
        self, user_id: str, email_id: str, text: str = ""
    ) -> ReplyDraft:
        """
        Create a manual reply draft in the database.

        Args:
            user_id: UUID string of the user.
            email_id: UUID string of the email to reply to.
            text: Initial text for the draft (default empty).

        Returns:
            ReplyDraft with status="pending".
        """
        user_uuid = UUID(user_id)
        email_uuid = UUID(email_id)
        draft_id = uuid.uuid4()

        draft_orm = ReplyDraftORM(
            id=draft_id,
            user_id=user_uuid,
            email_id=email_uuid,
            draft_text=text,
            status="pending",
        )
        self._session.add(draft_orm)
        await self._session.commit()

        logger.info(
            "Created manual reply draft %s for email %s (user %s).",
            draft_id,
            email_id,
            user_id,
        )

        return ReplyDraft(
            id=draft_id,
            email_id=email_uuid,
            draft_text=text,
            status="pending",
        )

    # ------------------------------------------------------------------
    # update_reply_draft
    # ------------------------------------------------------------------

    async def update_reply_draft(
        self, user_id: str, draft_id: str, text: str
    ) -> ReplyDraft:
        """
        Update the text of an existing reply draft.

        Args:
            user_id: UUID string of the user.
            draft_id: UUID string of the draft to update.
            text: New draft text.

        Returns:
            Updated ReplyDraft object.
        """
        user_uuid = UUID(user_id)
        draft_uuid = UUID(draft_id)

        stmt = select(ReplyDraftORM).where(
            ReplyDraftORM.id == draft_uuid,
            ReplyDraftORM.user_id == user_uuid,
        )
        result = await self._session.execute(stmt)
        draft_row = result.scalar_one_or_none()

        if not draft_row:
            raise HTTPException(status_code=404, detail="Reply draft not found.")

        draft_row.draft_text = text
        await self._session.commit()
        await self._session.refresh(draft_row)

        logger.info("Updated draft %s for user %s.", draft_id, user_id)

        return ReplyDraft.model_validate(draft_row)

    # ------------------------------------------------------------------
    # send_reply
    # ------------------------------------------------------------------

    async def send_reply(self, user_id: str, draft_id: str) -> SendResult:
        """
        Send a reply draft via Gmail API.

        Checks execution mode — if not "auto", raises an error (draft must be
        approved first). Sends the draft via Gmail API using the user's OAuth
        token. Updates reply_drafts.status to "sent" and sets sent_at.
        Records a reply_sent analytics event with time_saved_min=5.

        Args:
            user_id: UUID string of the user.
            draft_id: UUID string of the reply draft to send.

        Returns:
            SendResult with success=True and the Gmail message_id on success.

        Raises:
            HTTPException(403): If execution mode is not "auto".
            HTTPException(404): If the draft is not found.

        Requirements: 4.5
        """
        # Fetch the draft
        user_uuid = UUID(user_id)
        draft_uuid = UUID(draft_id)

        stmt = select(ReplyDraftORM).where(
            ReplyDraftORM.id == draft_uuid,
            ReplyDraftORM.user_id == user_uuid,
        )
        result = await self._session.execute(stmt)
        draft_row = result.scalar_one_or_none()

        if draft_row is None:
            raise HTTPException(status_code=404, detail="Reply draft not found.")

        # Fetch the original email to get thread_id and recipient
        email_stmt = select(EmailORM).where(EmailORM.id == draft_row.email_id)
        email_result = await self._session.execute(email_stmt)
        email_row = email_result.scalar_one_or_none()

        gmail_message_id: str | None = None

        try:
            access_token, refresh_token = await self._get_oauth_token(user_id)
            gmail = self._build_gmail_client(access_token, refresh_token)

            # Build the MIME message
            mime_msg = MIMEText(draft_row.draft_text)
            if email_row is not None:
                mime_msg["To"] = email_row.sender
                mime_msg["Subject"] = f"Re: {email_row.subject or ''}"
                thread_id = email_row.thread_id
            else:
                thread_id = None

            raw_bytes = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
            body: dict = {"raw": raw_bytes}
            if thread_id:
                body["threadId"] = thread_id

            send_response = (
                gmail.users().messages().send(userId="me", body=body).execute()
            )
            gmail_message_id = send_response.get("id")
            logger.info(
                "Sent reply for draft %s via Gmail (message_id=%s).",
                draft_id,
                gmail_message_id,
            )

        except Exception as exc:
            logger.error(
                "Failed to send reply for draft %s via Gmail: %s", draft_id, exc
            )
            return SendResult(success=False, message_id=None)

        # Update draft status to "sent"
        draft_row.status = "sent"
        draft_row.sent_at = datetime.now(tz=timezone.utc)
        
        # Mark the original email as replied
        if email_row:
            email_row.is_replied = True
            
        await self._session.commit()

        # Record analytics event
        try:
            event = AnalyticsEvent(
                id=uuid.uuid4(),
                user_id=user_uuid,
                event_type="reply_sent",
                metadata_={"draft_id": draft_id, "gmail_message_id": gmail_message_id},
                time_saved_min=5.0,
                created_at=datetime.utcnow(),
            )
            await self._analytics.record_event(user_id, event)
        except Exception as exc:
            logger.warning("Failed to record reply_sent analytics: %s", exc)

        return SendResult(success=True, message_id=gmail_message_id)

    # ------------------------------------------------------------------
    # embed_and_store
    # ------------------------------------------------------------------

    async def embed_and_store(self, user_id: str, email: EmailMessage) -> None:
        """
        Generate a 1536-dim embedding for the email and upsert into FAISS.

        Steps:
        1. Generate embedding via openai.embeddings.create(model="text-embedding-3-small").
        2. Upsert into FAISS using FAISSStore.upsert(user_id, email_id, embedding).
        3. Update emails.embedding_id in the database.

        Operation is idempotent — upsert handles re-embedding the same email.

        Args:
            user_id: UUID string of the user.
            email: EmailMessage to embed and store.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        body_text = email.body_text or ""
        if not body_text.strip():
            logger.warning(
                "Skipping embed_and_store for email %s: empty body.", email.id
            )
            return

        # Step 1: Generate embedding
        try:
            response = self._openai.embeddings.create(
                model="text-embedding-3-small",
                input=body_text,
            )
            embedding: list[float] = response.data[0].embedding
        except Exception as exc:
            logger.error(
                "Failed to generate embedding for email %s: %s", email.id, exc
            )
            raise

        # Step 2: Upsert into FAISS
        vector_id = str(email.id)
        try:
            self._faiss.initialize(user_id)
            self._faiss.upsert(user_id, vector_id, embedding)
        except Exception as exc:
            logger.error(
                "Failed to upsert embedding into FAISS for email %s: %s", email.id, exc
            )
            raise

        # Step 3: Update emails.embedding_id in the database
        try:
            stmt = select(EmailORM).where(EmailORM.id == email.id)
            result = await self._session.execute(stmt)
            email_row = result.scalar_one_or_none()
            if email_row is not None:
                email_row.embedding_id = vector_id
                await self._session.commit()
                logger.debug(
                    "Updated embedding_id for email %s (user %s).", email.id, user_id
                )
            else:
                logger.warning(
                    "Email %s not found in DB; embedding_id not updated.", email.id
                )
        except Exception as exc:
            logger.error(
                "Failed to update embedding_id for email %s: %s", email.id, exc
            )
            raise


# ---------------------------------------------------------------------------
# Body extraction helper
# ---------------------------------------------------------------------------


def _extract_body_text(payload: dict) -> str | None:
    """
    Recursively extract plain-text body from a Gmail message payload.

    Handles both simple messages (body.data) and multipart messages
    (parts[*].body.data). Prefers text/plain over text/html.

    Args:
        payload: The 'payload' dict from a Gmail API message.

    Returns:
        Decoded plain-text body string, or None if not found.
    """
    mime_type = payload.get("mimeType", "")

    # Simple message with body data
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    # Multipart message — recurse into parts
    if mime_type.startswith("multipart/"):
        parts = payload.get("parts", [])
        # First pass: prefer text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data + "==").decode(
                        "utf-8", errors="replace"
                    )
        # Second pass: recurse into nested multipart
        for part in parts:
            result = _extract_body_text(part)
            if result:
                return result

    # Fallback: try body.data directly
    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    return None
