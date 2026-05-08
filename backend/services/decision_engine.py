"""
Decision Engine service for the Clone Yourself Platform.

Constructs modular prompts and routes them to OpenAI GPT-4o. Parses structured
responses into typed Pydantic models.

Interface:
    - classify_email(email, user_prefs) → EmailClassification
    - generate_reply(email, style_ctx) → ReplyDraft
    - suggest_meeting_slots(email, free_slots) → list[MeetingSlot]
    - generate_daily_brief(context) → DailyBrief
    - suggest_followup(email, days_elapsed) → FollowupSuggestion

Requirements: 3.1, 3.2, 3.5, 3.6, 4.1, 4.7, 4.8, 6.6, 8.1, 12.3, 13.6
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Literal

import openai
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.pydantic_schemas import (
    BriefContext,
    DailyBrief,
    EmailMessage,
    FollowupSuggestion,
    MeetingSlot,
    ReplyDraft,
    StyleContext,
    TimeSlot,
    UserPreferences,
)
from utils.prompts import inject, load_prompt_template

logger = logging.getLogger(__name__)

# Type alias matching the Pydantic Literal on EmailMessage.classification
EmailClassification = Literal["urgent", "normal", "low"]

# Exponential backoff delays in seconds for RateLimitError retries
_BACKOFF_DELAYS = (2, 4, 8)
_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

# Patterns that could be used for prompt injection
_DOUBLE_BRACE_RE = re.compile(r"\{\{|\}\}")
_BACKTICK_SEQ_RE = re.compile(r"`{1,}")
# Matches lines that look like system-level instructions embedded in user content
_SYSTEM_INSTRUCTION_RE = re.compile(
    r"(ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|context)|"
    r"you\s+are\s+now\s+a?\s*\w*\s*(assistant|ai|bot|model)|"
    r"system\s*:\s*|"
    r"<\s*/?system\s*>|"
    r"\[INST\]|\[/INST\]|"
    r"###\s*(instruction|system|prompt))",
    re.IGNORECASE,
)


def _sanitize_body(text: str) -> str:
    """Strip characters and patterns that could be used for prompt injection.

    Removes:
    - ``{{`` and ``}}`` (template placeholder syntax)
    - Backtick sequences
    - Lines that look like embedded system instructions

    Args:
        text: Raw email body text.

    Returns:
        Sanitized text safe for injection into a prompt template.
    """
    # Remove double-brace sequences
    sanitized = _DOUBLE_BRACE_RE.sub("", text)
    # Remove backtick sequences
    sanitized = _BACKTICK_SEQ_RE.sub("", sanitized)
    # Remove lines that look like system instructions
    sanitized = _SYSTEM_INSTRUCTION_RE.sub("[REDACTED]", sanitized)
    return sanitized


# ---------------------------------------------------------------------------
# DecisionEngine
# ---------------------------------------------------------------------------


class DecisionEngine:
    """
    Routes LLM prompts to OpenAI GPT-4o and parses structured responses.

    Args:
        openai_client: An ``openai.AsyncOpenAI`` client instance.
        session: SQLAlchemy ``AsyncSession`` (reserved for future DB logging).
    """

    def __init__(
        self,
        openai_client: openai.AsyncOpenAI,
        session: AsyncSession,
    ) -> None:
        self._openai = openai_client
        self._session = session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_token_usage(self, method: str, usage: object) -> None:
        """Log token usage from an OpenAI API response.

        Args:
            method: Name of the calling method (for log context).
            usage: The ``usage`` object from the OpenAI response.
        """
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        logger.info(
            "[%s] token usage — prompt: %s, completion: %s, total: %s",
            method,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

    async def _call_openai(
        self,
        method: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict | None = None,
    ) -> str:
        """Call GPT-4o with exponential backoff retry on RateLimitError.

        Retries up to ``_MAX_RETRIES`` times with delays of 2s, 4s, 8s.

        Args:
            method: Caller name used in log messages.
            system_prompt: The system message content.
            user_prompt: The user message content.
            temperature: Sampling temperature.
            response_format: Optional ``response_format`` dict (e.g. JSON mode).

        Returns:
            The text content of the first choice in the response.

        Raises:
            openai.RateLimitError: If all retries are exhausted.
            openai.OpenAIError: For non-rate-limit API errors.
        """
        kwargs: dict = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._openai.chat.completions.create(**kwargs)
                self._log_token_usage(method, response.usage)
                return response.choices[0].message.content or ""
            except openai.RateLimitError as exc:
                if "insufficient_quota" in str(exc):
                    raise
                last_exc = exc
                delay = _BACKOFF_DELAYS[attempt]
                logger.warning(
                    "[%s] RateLimitError on attempt %d/%d; retrying in %ds.",
                    method,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            except openai.OpenAIError:
                raise

        # All retries exhausted — re-raise the last rate-limit error
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _parse_json(raw: str, method: str) -> dict | list:
        """Parse a JSON string, stripping markdown fences if present.

        Args:
            raw: Raw string from the LLM response.
            method: Caller name used in log messages.

        Returns:
            Parsed Python object (dict or list).

        Raises:
            ValueError: If the string cannot be parsed as JSON after cleanup.
        """
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("[%s] Failed to parse JSON response: %s\nRaw: %r", method, exc, raw)
            raise ValueError(f"[{method}] Malformed JSON from LLM: {exc}") from exc

    # ------------------------------------------------------------------
    # classify_email
    # ------------------------------------------------------------------

    async def classify_email(
        self,
        email: EmailMessage,
        user_prefs: UserPreferences,
    ) -> EmailClassification:
        """Classify an email as urgent, normal, or low priority.

        Uses the ``email_classification`` prompt template with ``temperature=0``
        for deterministic output. On exhausted retries returns ``"normal"`` as
        a safe default.

        Args:
            email: The email to classify.
            user_prefs: User preferences (tone, working hours, etc.).

        Returns:
            One of ``"urgent"``, ``"normal"``, or ``"low"``.

        Requirements: 3.1, 3.2, 3.5, 3.6, 4.1
        """
        method = "classify_email"
        body = _sanitize_body(email.body_text or "")[:1500]
        subject = email.subject or "(no subject)"
        sender = email.sender

        system_prompt = load_prompt_template("email_classification")
        user_prompt = (
            f"From: {sender}\n"
            f"Subject: {subject}\n\n"
            f"{body}"
        )

        try:
            raw = await self._call_openai(
                method=method,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except openai.RateLimitError:
            if not getattr(self.__class__, "_quota_exhausted", False):
                logger.error("[%s] All retries exhausted; returning default 'normal'.", method)
            return "normal"
        except openai.OpenAIError as exc:
            logger.error("[%s] OpenAI error: %s; returning default 'normal'.", method, exc)
            return "normal"

        try:
            parsed = self._parse_json(raw, method)
        except ValueError:
            return "normal"

        classification = parsed.get("classification", "normal")  # type: ignore[union-attr]
        if classification not in ("urgent", "normal", "low"):
            logger.warning(
                "[%s] Unexpected classification value %r; defaulting to 'normal'.",
                method,
                classification,
            )
            return "normal"

        return classification  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # generate_reply
    # ------------------------------------------------------------------

    async def generate_reply(
        self,
        email: EmailMessage,
        style_ctx: StyleContext,
    ) -> ReplyDraft:
        """Generate a reply draft in the user's tone and style.

        Uses the ``reply_generation`` prompt template with ``temperature=0.7``.
        Injects tone from ``style_ctx.tone`` and formats ``style_ctx.similar_emails``
        as example text.

        Args:
            email: The email to reply to.
            style_ctx: Writing style context (tone + similar past emails).

        Returns:
            A ``ReplyDraft`` with ``status="pending"``.

        Requirements: 3.1, 4.1, 4.7, 4.8
        """
        method = "generate_reply"
        body = _sanitize_body(email.body_text or "")[:3000]

        # Format similar emails as examples text
        examples_parts: list[str] = []
        for i, past_email in enumerate(style_ctx.similar_emails, start=1):
            past_body = _sanitize_body(past_email.body_text or "")
            examples_parts.append(f"Example {i}:\n{past_body}")
        examples_text = "\n\n".join(examples_parts) if examples_parts else "(no examples available)"

        system_prompt = load_prompt_template("reply_generation")
        system_prompt = inject(system_prompt, "tone", style_ctx.tone)
        system_prompt = inject(system_prompt, "examples", examples_text)

        user_prompt = f"Reply to this email:\n\n{body}"

        try:
            raw = await self._call_openai(
                method=method,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
            )
        except openai.OpenAIError as exc:
            logger.error("[%s] OpenAI error: %s; returning default error draft.", method, exc)
            raw = "Error generating reply: OpenAI API limit reached or unavailable."

        return ReplyDraft(
            id=uuid.uuid4(),
            email_id=email.id,
            draft_text=raw.strip(),
            status="pending",
        )

    # ------------------------------------------------------------------
    # suggest_meeting_slots
    # ------------------------------------------------------------------

    async def suggest_meeting_slots(
        self,
        email: EmailMessage,
        free_slots: list[TimeSlot],
    ) -> list[MeetingSlot]:
        """Suggest up to 3 meeting time slots from the user's free calendar slots.

        Uses the ``meeting_slot_suggestion`` prompt template with ``temperature=0``.
        Injects the email body and free slots as JSON.

        Args:
            email: The meeting-request email.
            free_slots: List of available time slots from the calendar.

        Returns:
            Up to 3 ``MeetingSlot`` objects ranked by confidence.

        Requirements: 6.6
        """
        method = "suggest_meeting_slots"
        body = _sanitize_body(email.body_text or "")[:2000]

        # Serialize free slots to JSON for injection
        slots_data = [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
            }
            for slot in free_slots
        ]
        slots_json = json.dumps(slots_data, indent=2)

        system_prompt = load_prompt_template("meeting_slot_suggestion")
        user_prompt = (
            f"Email requesting a meeting:\n{body}\n\n"
            f"Available free slots:\n{slots_json}"
        )

        try:
            raw = await self._call_openai(
                method=method,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0,
            )
        except openai.OpenAIError as exc:
            logger.error("[%s] OpenAI error: %s; returning empty list.", method, exc)
            return []

        try:
            parsed = self._parse_json(raw, method)
        except ValueError:
            return []

        if not isinstance(parsed, list):
            logger.error("[%s] Expected JSON array, got %s.", method, type(parsed).__name__)
            return []

        meeting_slots: list[MeetingSlot] = []
        for item in parsed:
            try:
                slot_data = item.get("slot", {})
                slot = TimeSlot(
                    start=datetime.fromisoformat(slot_data["start"]),
                    end=datetime.fromisoformat(slot_data["end"]),
                )
                confidence = float(item.get("confidence_score", 0.5))
                # Clamp to [0.0, 1.0]
                confidence = max(0.0, min(1.0, confidence))
                reason = str(item.get("reason", ""))
                meeting_slots.append(
                    MeetingSlot(slot=slot, confidence_score=confidence, reason=reason)
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("[%s] Skipping malformed slot item: %s", method, exc)
                continue

        # Return top 3
        return meeting_slots[:3]

    # ------------------------------------------------------------------
    # generate_daily_brief
    # ------------------------------------------------------------------

    async def generate_daily_brief(self, context: BriefContext) -> DailyBrief:
        """Generate a daily brief with exactly 3 urgent items, 2 followups, 1 risk.

        Uses the ``daily_brief`` prompt template with ``temperature=0.7``.
        Injects all four context fields. Validates the parsed response structure.

        Args:
            context: ``BriefContext`` with urgent emails, followups, events, and stats.

        Returns:
            A ``DailyBrief`` with exactly 3 urgent items, 2 followups, and 1 risk.

        Requirements: 8.1
        """
        method = "generate_daily_brief"

        # Serialize context fields for injection
        urgent_emails_text = json.dumps(
            [
                {
                    "subject": e.subject,
                    "sender": e.sender,
                    "body_preview": _sanitize_body((e.body_text or "")[:200]),
                }
                for e in context.urgent_emails
            ],
            indent=2,
        )

        followups_text = json.dumps(
            [
                {
                    "subject": f.subject,
                    "sender": f.sender,
                    "days_elapsed": f.days_elapsed,
                }
                for f in context.pending_followups
            ],
            indent=2,
        )

        upcoming_events_text = json.dumps(
            [
                {
                    "title": ev.title,
                    "start_time": ev.start_time.isoformat(),
                    "end_time": ev.end_time.isoformat(),
                }
                for ev in context.upcoming_events
            ],
            indent=2,
        )

        analytics_text = json.dumps(
            {
                "actions_automated": context.analytics_stats.actions_automated,
                "time_saved_minutes": context.analytics_stats.time_saved_minutes,
                "emails_classified": context.analytics_stats.emails_classified,
                "replies_sent": context.analytics_stats.replies_sent,
                "events_created": context.analytics_stats.events_created,
            },
            indent=2,
        )

        system_prompt = load_prompt_template("daily_brief")
        system_prompt = inject(system_prompt, "urgent_emails", urgent_emails_text)
        system_prompt = inject(system_prompt, "followups", followups_text)
        system_prompt = inject(system_prompt, "upcoming_events", upcoming_events_text)
        system_prompt = inject(system_prompt, "analytics", analytics_text)

        user_prompt = "Generate the daily brief based on the context above."

        try:
            raw = await self._call_openai(
                method=method,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            parsed = self._parse_json(raw, method)
        except (openai.OpenAIError, ValueError) as exc:
            logger.error("[%s] Failed to generate brief: %s; returning default fallback.", method, exc)
            return DailyBrief(
                urgent_items=["Unable to generate AI brief.", "OpenAI API quota exceeded or unavailable.", "Please check your OpenAI billing details."],
                followups=["Unable to generate follow-ups.", "API limits reached."],
                risk="API Limits Reached. The AI features are temporarily unavailable.",
                generated_at=datetime.utcnow(),
            )

        # Validate structure — enforce exactly 3 urgent items, 2 followups, 1 risk
        urgent_items: list[str] = list(parsed.get("urgent_items", []))  # type: ignore[union-attr]
        followups: list[str] = list(parsed.get("followups", []))  # type: ignore[union-attr]
        risk: str = str(parsed.get("risk", ""))  # type: ignore[union-attr]

        # Pad or truncate to meet exact counts
        while len(urgent_items) < 3:
            urgent_items.append("No additional urgent items.")
        urgent_items = urgent_items[:3]

        while len(followups) < 2:
            followups.append("No additional follow-ups.")
        followups = followups[:2]

        if not risk:
            risk = "No significant risks identified."

        return DailyBrief(
            urgent_items=urgent_items,
            followups=followups,
            risk=risk,
            generated_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # suggest_followup
    # ------------------------------------------------------------------

    async def suggest_followup(
        self,
        email: EmailMessage,
        days_elapsed: int,
    ) -> FollowupSuggestion:
        """Generate a follow-up message for an unanswered email.

        Uses the ``followup_suggestion`` prompt template with ``temperature=0.7``.
        Injects ``days_elapsed`` and the user's tone (defaults to ``"casual"``
        when not available from context).

        Args:
            email: The original sent email that has not received a reply.
            days_elapsed: Number of days since the email was sent.

        Returns:
            A ``FollowupSuggestion`` with a draft follow-up message.

        Requirements: 4.7, 4.8
        """
        method = "suggest_followup"
        body = _sanitize_body(email.body_text or "")

        # Default tone to casual; callers may pass a richer email with tone info
        tone = "casual"

        system_prompt = load_prompt_template("followup_suggestion")
        system_prompt = inject(system_prompt, "days_elapsed", str(days_elapsed))
        system_prompt = inject(system_prompt, "tone", tone)

        user_prompt = (
            f"Original email subject: {email.subject or '(no subject)'}\n\n"
            f"Original email body:\n{body}"
        )

        try:
            raw = await self._call_openai(
                method=method,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
            )
        except openai.OpenAIError as exc:
            logger.error("[%s] OpenAI error: %s; returning empty draft.", method, exc)
            raw = ""

        return FollowupSuggestion(
            id=uuid.uuid4(),
            email_id=email.id,
            sender=email.sender,
            subject=email.subject,
            sent_at=email.received_at,
            days_elapsed=days_elapsed,
            draft_text=raw.strip() or "Hi, just following up on my previous email. Please let me know if you have any updates.",
            status="pending",
        )
