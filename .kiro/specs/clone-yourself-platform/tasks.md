# Implementation Plan: Clone Yourself Platform

## Overview

Implement the Clone Yourself Platform — an AI-powered personal digital worker — in eight sequential phases: backend scaffolding, database layer, AI services, API endpoints, Next.js frontend, frontend-backend integration, demo seed data, and final testing. The backend is Python/FastAPI; the frontend is Next.js/TypeScript. All eight correctness properties from the design are covered by property-based tests (hypothesis) and unit tests.

---

## Tasks

- [x] 1. Set up backend project structure
  - Create `/backend/` directory tree: `api/`, `services/`, `models/`, `schemas/`, `utils/`
  - Write `backend/requirements.txt` with pinned versions for all dependencies from the design: `fastapi==0.111.*`, `uvicorn==0.30.*`, `sqlalchemy==2.0.*`, `asyncpg==0.29.*`, `alembic==1.13.*`, `openai==1.35.*`, `faiss-cpu==1.8.*`, `google-auth-oauthlib==1.2.*`, `google-api-python-client==2.134.*`, `python-jose==3.3.*`, `cryptography==42.0.*`, `slowapi==0.1.*`, `pydantic==2.7.*`, `httpx==0.27.*`, `python-dotenv==1.0.*`, `hypothesis==6.100.*`, `pytest-asyncio==0.23.*`, `pytest==8.*`
  - Write `.env.example` with placeholder keys: `DATABASE_URL`, `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `JWT_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `FRONTEND_URL`, `ENVIRONMENT`
  - Write `backend/main.py` with FastAPI app instantiation, CORS middleware (restrict to `FRONTEND_URL` in production, `*` in dev), `slowapi` rate-limit middleware, and router includes for all six API modules
  - _Requirements: 12.5, 12.1_

- [x] 2. Set up database layer
  - [x] 2.1 Write `database/schema.sql` with all seven tables from the design: `users`, `oauth_tokens`, `user_preferences`, `emails`, `reply_drafts`, `calendar_events`, `followups`, `analytics_events`, plus all four indexes
    - _Requirements: 1.3, 3.4, 4.3, 7.3, 11.1_
  - [x] 2.2 Write `backend/models/db_models.py` with SQLAlchemy 2.0 ORM mapped classes for all seven tables, using `mapped_column` and `Mapped` typed annotations; include all foreign key relationships and cascade rules from the schema
    - _Requirements: 1.3, 3.4, 4.3_
  - [x] 2.3 Write `backend/schemas/pydantic_schemas.py` with all Pydantic v2 models from the design: `User`, `UserPreferences`, `EmailMessage`, `ReplyDraft`, `TimeSlot`, `MeetingSlot`, `DashboardPayload`, `AnalyticsStats`, `DailyBrief`, `StyleContext`, `BriefContext`, `FollowupSuggestion`, `AnalyticsEvent`, `CalendarEvent`, `TokenResponse`, `GenerateReplyRequest`, `CalendarSuggestRequest`
    - _Requirements: 3.1, 4.3, 6.7, 8.1, 8.2, 8.3_
  - [x] 2.4 Initialise Alembic in `backend/` and create the initial migration from `db_models.py`; write `alembic/env.py` to read `DATABASE_URL` from environment and use async engine
    - _Requirements: 2.1_

- [x] 3. Implement AI utility layer
  - [x] 3.1 Write `backend/utils/token_encryption.py` implementing AES-256 encrypt/decrypt helpers using the `cryptography` library; load the key from `TOKEN_ENCRYPTION_KEY` env var; never hardcode the key
    - _Requirements: 1.3, 12.1_
  - [x] 3.2 Write `backend/utils/prompts.py` with the five modular prompt templates from the design: `email_classification`, `reply_generation`, `meeting_slot_suggestion`, `daily_brief`, `followup_suggestion`; implement `load_prompt_template(name)` and `inject(template, key, value)` helpers
    - _Requirements: 3.1, 4.1, 6.6, 8.1_
  - [x] 3.3 Write `backend/utils/faiss_store.py` implementing `FAISSStore` class with methods: `initialize(user_id)`, `upsert(user_id, vector_id, embedding)`, `search(user_id, query_embedding, top_k)`, `exists(user_id)`; use per-user flat index files; handle missing index by initialising empty index
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 13.3_
  - [x] 3.4 Write `backend/utils/mock_data.py` with sample `EmailMessage` objects (including a meeting-request email, an action-required email, and a low-priority newsletter), sample `CalendarEvent` objects, and sample `AnalyticsStats`; used as fallback when external APIs are unavailable
    - _Requirements: 13.2, 13.3, 14.1_

- [ ] 4. Implement backend services
  - [x] 4.1 Write `backend/services/behavior_engine.py` implementing `BehaviorEngine` with all five interface methods from the design; persist and retrieve `UserPreferences` from `user_preferences` table; implement `get_writing_style_context` to query FAISS for top-5 similar emails and return a `StyleContext`; implement `record_user_action` to store edit feedback
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 4.9_
  - [x] 4.2 Write `backend/services/decision_engine.py` implementing `DecisionEngine` with all five interface methods; use `prompts.py` templates; implement exponential backoff retry (2s, 4s, 8s, max 3 attempts) for `openai.RateLimitError`; sanitize email body text before prompt injection; parse GPT-4o JSON responses into typed Pydantic models; log token usage per call
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 4.1, 4.7, 4.8, 6.6, 8.1, 12.3, 13.6_
  - [x] 4.3 Write `backend/services/analytics_service.py` implementing `AnalyticsService` with all four interface methods; compute `actions_automated` as `COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)`; use constants 5 min/reply and 10 min/event for time saved; support `week` and `month` period filters
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  - [x] 4.4 Write `backend/services/email_service.py` implementing `EmailService` with all six interface methods; authenticate Gmail API calls with decrypted OAuth token; implement `embed_and_store` to generate 1536-dim embeddings via `text-embedding-3-small` and upsert into FAISS; fall back to `mock_data.py` when Gmail API is unavailable; enforce execution mode when sending replies
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 13.2_
  - [x] 4.5 Write `backend/services/calendar_service.py` implementing `CalendarService` with all four interface methods; implement `get_free_slots` using the pseudocode algorithm from the design (30-min granularity, working-hours filter, conflict check, ascending sort); fall back to mock slots when Calendar API is unavailable and flag with `{"source": "mock", "reason": "calendar_unavailable"}`; limit `suggest_meeting_times` to top 3 ranked slots
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 13.3_
  - [x] 4.6 Write `backend/services/followup_agent.py` implementing `FollowupAgent` with all four interface methods; query emails older than `followup_threshold` days with `is_replied = FALSE` and no active pending/snoozed/resolved followup; upsert followup records to enforce at-most-one-pending-per-email; sort results by `sent_at` ascending
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  - [x] 4.7 Write `backend/services/task_orchestrator.py` implementing `TaskOrchestrator` with all five interface methods; use `asyncio.gather()` for concurrent email, analytics, and brief fetching on dashboard load; handle partial service failures by returning available data; enforce execution mode for all actions
    - _Requirements: 2.1, 2.2, 2.4, 10.1, 10.2, 10.3, 10.4_
  - [x] 4.8 Write `backend/services/file_brain.py` implementing `FileBrain` with a `get_demo_files()` method returning mock file objects and a `simulate_organize(file_id)` method that returns a simulated rename/categorize result without touching real files
    - _Requirements: 14.1, 14.2_

- [x] 5. Checkpoint — backend services complete
  - Ensure all backend service files are importable without errors
  - Run `python -m pytest backend/ -x --ignore=backend/api` to verify unit tests pass
  - Ask the user if any questions arise before proceeding to API layer

- [ ] 6. Build backend API endpoints
  - [x] 6.1 Write `backend/api/auth.py` with four FastAPI routes: `GET /auth/google` (OAuth redirect), `GET /auth/callback` (code exchange, token encryption, JWT issue), `POST /auth/refresh`, `POST /auth/revoke`; implement `get_current_user` dependency that validates JWT and never returns token values in response body; auto-refresh expired tokens before retrying
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 12.2_
  - [x] 6.2 Write `backend/api/emails.py` with routes: `GET /emails` (fetch + classify), `GET /emails/{id}`, `POST /emails/generate-reply` (rate-limited 30 req/min), `POST /emails/{id}/send-reply`, `POST /emails/{id}/embed`; wire to `EmailService` and `TaskOrchestrator`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 12.4_
  - [x] 6.3 Write `backend/api/calendar.py` with routes: `GET /calendar/free-slots`, `POST /calendar/suggest` (rate-limited 30 req/min), `POST /calendar/events`; wire to `CalendarService` and `DecisionEngine`
    - _Requirements: 6.1, 6.6, 6.7, 6.8, 12.4_
  - [x] 6.4 Write `backend/api/dashboard.py` with route `GET /dashboard`; delegate to `TaskOrchestrator.get_dashboard()`; return `DashboardPayload` including `followup_count`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 6.5 Write `backend/api/followup.py` with routes: `GET /followups`, `POST /followups/{id}/snooze`, `POST /followups/{id}/resolve`, `POST /followups/{id}/generate-draft`; wire to `FollowupAgent`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  - [x] 6.6 Write `backend/api/analytics.py` with routes: `GET /analytics/stats`, `GET /analytics/time-saved`, `GET /analytics/actions`; wire to `AnalyticsService`
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 7. Checkpoint — full backend runnable
  - Start `uvicorn backend.main:app --reload` and verify `/docs` loads all routes
  - Run `python -m pytest backend/ -x` to confirm all backend tests pass
  - Ask the user if any questions arise before proceeding to frontend

- [ ] 8. Build frontend project structure and types
  - [x] 8.1 Initialise Next.js 14 project in `/frontend/` with TypeScript, Tailwind CSS, and `next-auth`; install all frontend dependencies from the design at pinned versions: `next@14.2.*`, `react@18.3.*`, `tailwindcss@3.4.*`, `axios@1.7.*`, `swr@2.2.*`, `react-window@1.8.*`, `recharts@2.12.*`, `@headlessui/react@2.1.*`, `next-auth@4.24.*`
    - _Requirements: 2.1_
  - [x] 8.2 Write `frontend/types/index.ts` with all TypeScript interfaces from the design: `User`, `Email`, `EmailClassification`, `ExecutionMode`, `DraftStatus`, `ReplyDraft`, `MeetingSlot`, `DashboardPayload`, `AnalyticsStats`, `DailyBrief`, `UserPreferences`
    - _Requirements: 3.1, 4.3, 6.7, 8.1_
  - [x] 8.3 Write `frontend/services/api.ts` with a typed axios client; implement all API call functions: `getDashboard()`, `getEmails()`, `generateReply(emailId)`, `sendReply(draftId)`, `getCalendarSlots()`, `suggestMeetingTimes(emailId)`, `createCalendarEvent(slot, attendees)`, `getFollowups()`, `snoozeFollowup(id, until)`, `resolveFollowup(id)`, `getAnalyticsStats()`, `getDailyBrief()`, `getUserPreferences()`, `updatePreferences(prefs)`; attach JWT from session to all requests
    - _Requirements: 1.4, 2.1, 4.4_

- [ ] 9. Build frontend components
  - [x] 9.1 Write `frontend/components/Navbar.tsx` with navigation links to Dashboard, Emails, Calendar, Analytics; show logged-in user avatar and name from session; include sign-out button
    - _Requirements: 2.1_
  - [x] 9.2 Write `frontend/components/EmailCard.tsx` accepting an `Email` prop; display subject, sender, received time, classification badge (colour-coded: red=urgent, yellow=normal, gray=low), and category tag; include a "Generate Reply" button that opens `EmailReplyPanel`
    - _Requirements: 3.1, 3.2_
  - [x] 9.3 Write `frontend/components/EmailReplyPanel.tsx` matching the design example; call `generateReply()` on button click; render editable textarea with draft text; call `sendReply()` on send; call `updatePreferences` to record edit if user modifies draft text
    - _Requirements: 4.1, 4.3, 4.4, 4.9_
  - [x] 9.4 Write `frontend/components/CalendarSuggestionPanel.tsx` accepting a list of `MeetingSlot` props; display up to 3 ranked slots with confidence score and reason; include "Confirm" button per slot that calls `createCalendarEvent()`
    - _Requirements: 6.7, 6.8_
  - [x] 9.5 Write `frontend/components/AnalyticsWidget.tsx` accepting `AnalyticsStats` prop; display `actionsAutomated`, `timeSavedMinutes`, `emailsClassified`, `repliesSent`, `eventsCreated` using `recharts` bar or stat cards
    - _Requirements: 11.4_
  - [x] 9.6 Write `frontend/components/DailyBriefPanel.tsx` that calls `getDailyBrief()` on mount; render exactly 3 urgent items, 2 follow-up items, and 1 risk string in distinct sections
    - _Requirements: 8.1, 8.2, 8.3_
  - [x] 9.7 Write `frontend/components/FollowupList.tsx` that accepts a list of `FollowupSuggestion` props; display sender, days elapsed, draft preview; include "Snooze" and "Resolve" action buttons wired to `snoozeFollowup()` and `resolveFollowup()`
    - _Requirements: 7.4, 7.6, 7.7_

- [ ] 10. Build frontend hooks and pages
  - [x] 10.1 Write `frontend/hooks/useDashboard.ts` using SWR to fetch `/dashboard`; return `{ data, isLoading, error, mutate }`
    - _Requirements: 2.1, 2.4_
  - [x] 10.2 Write `frontend/hooks/useEmails.ts` using SWR to fetch `/emails`; return `{ emails, isLoading, error, mutate }`
    - _Requirements: 3.1_
  - [x] 10.3 Write `frontend/hooks/useAnalytics.ts` using SWR to fetch `/analytics/stats`; return `{ stats, isLoading, error }`
    - _Requirements: 11.4_
  - [x] 10.4 Write `frontend/pages/api/auth/[...nextauth].ts` configuring `next-auth` with Google OAuth provider using `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`; request scopes `gmail.readonly gmail.send calendar.readonly calendar.events`; store JWT in session
    - _Requirements: 1.1, 1.2, 12.6_
  - [x] 10.5 Write `frontend/pages/index.tsx` that redirects authenticated users to `/dashboard` and unauthenticated users to the Google sign-in page
    - _Requirements: 1.1_
  - [x] 10.6 Write `frontend/pages/dashboard.tsx` matching the design example; use `useDashboard` hook; render `EmailCard` list (col-span-8), `AnalyticsWidget`, `DailyBriefPanel`, and follow-up count badge (col-span-4); show loading skeleton while fetching
    - _Requirements: 2.1, 2.3, 8.1_
  - [x] 10.7 Write `frontend/pages/emails.tsx` using `useEmails` hook; render full email list with `EmailCard` and inline `EmailReplyPanel`; support filtering by classification
    - _Requirements: 3.1, 4.1_
  - [x] 10.8 Write `frontend/pages/calendar.tsx` that fetches free slots and renders `CalendarSuggestionPanel`; display upcoming calendar events list
    - _Requirements: 6.1, 6.7_
  - [x] 10.9 Write `frontend/pages/analytics.tsx` using `useAnalytics` hook; render `AnalyticsWidget` with full stats and a `recharts` time-series chart of actions over the past week
    - _Requirements: 11.4_

- [x] 11. Connect frontend and backend
  - Configure `frontend/next.config.ts` with `NEXT_PUBLIC_API_URL` env var pointing to the FastAPI backend; set up API proxy rewrites so `/api/backend/*` proxies to the FastAPI server
  - Update `backend/main.py` CORS middleware to read allowed origins from `FRONTEND_URL` env var; confirm `allow_credentials=True` and correct allowed methods/headers
  - Update `frontend/services/api.ts` base URL to use `NEXT_PUBLIC_API_URL`; add axios request interceptor to attach `Authorization: Bearer <token>` from `next-auth` session to every request
  - Write `frontend/.env.local.example` with `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NEXT_PUBLIC_API_URL`
  - _Requirements: 1.4, 12.5_

- [x] 12. Add demo seed data
  - Write `backend/utils/mock_data.py` (extend existing) with a `seed_demo_data(db_session)` function that inserts: 1 demo user with preferences, 5 sample emails (mix of urgent/normal/low, including a meeting-request), 2 pending reply drafts, 3 calendar events, 2 pending followups, and 10 analytics events spanning the past week
  - Write `backend/seed.py` as a standalone script that creates a DB session, calls `seed_demo_data()`, and prints a summary; run with `python backend/seed.py`
  - _Requirements: 14.1, 14.2_

- [ ] 13. Write unit tests
  - [x] 13.1 Write `backend/tests/test_decision_engine.py` with unit tests for `classify_email` (urgent/normal/low paths, default-on-exhausted-retries), `generate_reply` (tone injection, empty similar-emails fallback), `suggest_meeting_slots` (top-3 limit), `generate_daily_brief` (structure validation), and exponential backoff retry logic using `AsyncMock`
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 4.1, 4.7, 4.8, 8.1, 8.2, 8.3_
  - [x] 13.2 Write `backend/tests/test_analytics_service.py` with unit tests verifying `actions_automated = COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)`, time-saved constants (5 min/reply, 10 min/event), and period filtering
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  - [x] 13.3 Write `backend/tests/test_followup_agent.py` with unit tests for: threshold filtering (only emails older than N days), exclusion of snoozed/resolved/sent followups, at-most-one-pending enforcement, ascending sort order, and snooze/resolve status transitions
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6, 7.7_
  - [x] 13.4 Write `backend/tests/test_token_encryption.py` with unit tests verifying encrypt→decrypt round-trip, that encrypted ciphertext differs from plaintext, and that decryption with a wrong key raises an error
    - _Requirements: 1.3, 12.1_
  - [x] 13.5 Write `backend/tests/test_auth_api.py` with unit tests verifying that no API response body contains an OAuth token value (test all auth endpoints), and that protected endpoints return 401 for missing/invalid JWT
    - _Requirements: 1.4, 1.8, 12.2_

- [ ] 14. Write property-based tests
  - [x] 14.1 Write `backend/tests/test_properties_calendar.py` using `hypothesis`
    - [x] 14.1.1 Write property test for slot validity (Property 3)
      - **Property 3: Free Slot Validity** — for any `working_start ∈ [6,11]`, `working_end ∈ [14,20]`, `meeting_duration ∈ {15,30,45,60}`, and `working_days ⊆ {1..7}`, every slot returned by `get_free_slots` satisfies `slot.start.time() >= working_hours_start`, `slot.end.time() <= working_hours_end`, `slot.start.isoweekday() ∈ working_days`, and no overlap with injected calendar events
      - Use `@given(st.integers(min_value=6, max_value=11), st.integers(min_value=14, max_value=20), st.sampled_from([15, 30, 45, 60]))`
      - **Validates: Requirements 6.1, 6.2, 6.3**
  - [x] 14.2 Write `backend/tests/test_properties_classification.py` using `hypothesis`
    - [x] 14.2.1 Write property test for classification completeness (Property 1)
      - **Property 1: Classification Completeness** — for any non-empty email body string, `classify_email` returns a value in `{"urgent", "normal", "low"}` (mock OpenAI to return each label deterministically; also test the default-on-failure path)
      - Use `@given(st.text(min_size=10, max_size=500))`
      - **Validates: Requirements 3.1**
  - [x] 14.3 Write `backend/tests/test_properties_analytics.py` using `hypothesis`
    - [x] 14.3.1 Write property test for analytics consistency (Property 5)
      - **Property 5: Analytics Consistency** — for any list of analytics events with types drawn from `{"reply_sent", "event_created", "followup_sent", "email_classified"}`, `get_dashboard_stats().actions_automated` equals `COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)`
      - Use `@given(st.lists(st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]), min_size=0, max_size=50))`
      - **Validates: Requirements 11.1, 11.2**
  - [x] 14.4 Write `backend/tests/test_properties_execution_mode.py` using `hypothesis`
    - [x] 14.4.1 Write property test for execution mode enforcement (Property 8)
      - **Property 8: Execution Mode Enforcement** — for any execution mode in `{"suggest", "approval", "auto"}` and any generated draft, the draft is sent to Gmail if and only if mode is `"auto"`; in `"suggest"` or `"approval"` mode the Gmail send function is never called
      - Use `@given(st.sampled_from(["suggest", "approval", "auto"]))`
      - **Validates: Requirements 10.1, 10.2, 10.3**

- [ ] 15. Write integration tests
  - [x] 15.1 Write `backend/tests/integration/test_email_flow.py` implementing the full email → classify → draft → dashboard integration test from the design
    - Use a test PostgreSQL database (or SQLite for CI) and mock Gmail + OpenAI APIs
    - Step 1: Insert a sample meeting-request email via mock Gmail
    - Step 2: `GET /emails` — assert 200, emails returned, classification assigned
    - Step 3: `POST /emails/generate-reply` — assert 200, `draft_text` non-empty, `status == "pending"`
    - Step 4: `GET /dashboard` — assert the email appears in `priorityEmails`
    - Step 5: Assert no OAuth token appears in any response body (Property 6)
    - _Requirements: 2.1, 3.1, 4.3, 1.8, 12.2_
  - [x] 15.2 Write `backend/tests/integration/test_followup_dedup.py` verifying that running `check_pending_followups` twice for the same email produces exactly one pending followup record (Property 4)
    - _Requirements: 7.2, 7.3_
  - [x] 15.3 Write `backend/tests/integration/test_daily_brief_structure.py` verifying that `generate_daily_brief` always returns exactly 3 urgent items, 2 followups, and 1 non-empty risk string across varied context inputs (Property 7)
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 16. Final checkpoint — all tests pass
  - Run `python -m pytest backend/ -v` and confirm all unit, property, and integration tests pass
  - Run `cd frontend && npm run build` and confirm no TypeScript or build errors
  - Ask the user if any questions arise before considering the implementation complete

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for full traceability to `requirements.md`
- Checkpoints (tasks 5, 7, 16) ensure incremental validation at natural phase boundaries
- Property tests use `hypothesis` and validate the eight correctness properties from `design.md`
- Unit tests use `pytest-asyncio` with `AsyncMock` for all async service methods
- Integration tests use a dedicated test database; never run against production data
- The seed script (task 12) enables demo mode without requiring live Google API credentials
- CORS and token security (tasks 11, 6.1) must be verified before any production deployment
