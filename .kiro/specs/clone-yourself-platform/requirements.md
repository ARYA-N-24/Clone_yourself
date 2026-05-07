# Requirements Document

## Introduction

The Clone Yourself Platform is an AI-powered personal digital worker that learns a user's communication style and behavioral patterns to automate repetitive workflows. The system integrates with Gmail and Google Calendar to handle email classification, reply drafting, meeting scheduling, and follow-up tracking — all while mimicking the user's tone and preferences.

The platform provides three automation modes (Suggest, Approval, Auto) that give users control over how aggressively the AI acts on their behalf. The MVP focuses on three core demo flows: email reply generation in the user's tone, meeting time suggestion from calendar free slots, and a unified dashboard that surfaces priority actions and productivity metrics.

This requirements document is derived from the approved design document and is traceable to the eight correctness properties defined therein.

---

## Glossary

- **Platform**: The Clone Yourself Platform system as a whole
- **Auth_Service**: The backend component responsible for Google OAuth 2.0 login, token exchange, and session management
- **Task_Orchestrator**: The central backend coordinator that routes requests to appropriate services and aggregates results
- **Behavior_Engine**: The backend component that stores and retrieves user behavioral preferences, tone, and style context
- **Decision_Engine**: The LLM prompt router that constructs modular prompts and routes them to OpenAI GPT-4o
- **Email_Service**: The backend component that fetches emails from Gmail API, stores them, and coordinates classification and reply generation
- **Calendar_Service**: The backend component that integrates with Google Calendar to read free/busy slots and create events
- **Followup_Agent**: The backend component that monitors sent emails for missing replies and surfaces follow-up suggestions
- **Analytics_Service**: The backend component that tracks automated actions and computes productivity metrics
- **Dashboard**: The unified frontend view showing priority emails, pending replies, suggested actions, follow-up count, and analytics
- **ReplyDraft**: An AI-generated email reply with a lifecycle status of pending, approved, sent, or discarded
- **ExecutionMode**: The user-configured automation level — one of `suggest`, `approval`, or `auto`
- **TimeSlot**: A calendar time window defined by a start and end datetime
- **MeetingSlot**: A ranked TimeSlot with a confidence score and reason, suitable for meeting scheduling
- **FollowupSuggestion**: A detected unreplied sent email with an AI-generated follow-up draft
- **DailyBrief**: A structured AI-generated summary containing exactly 3 urgent items, 2 follow-ups, and 1 risk
- **StyleContext**: A user-specific context object containing tone preference and semantically similar past email examples
- **FAISS**: The in-process vector similarity search index used to retrieve semantically similar past emails
- **GPT-4o**: The OpenAI language model used for email classification, reply generation, meeting slot ranking, and brief generation
- **OAuth_Token**: A Google OAuth access or refresh token used to authenticate calls to Gmail and Calendar APIs

---

## Requirements

### Requirement 1: Google OAuth Authentication

**User Story:** As a user, I want to sign in with my Google account, so that the platform can securely access my Gmail and Google Calendar on my behalf.

#### Acceptance Criteria

1. WHEN a user initiates login, THE Auth_Service SHALL redirect the user to the Google OAuth 2.0 consent screen with the minimum required scopes: `gmail.readonly`, `gmail.send`, `calendar.readonly`, and `calendar.events`
2. WHEN Google redirects back with an authorization code, THE Auth_Service SHALL exchange the code for an access token and a refresh token
3. THE Auth_Service SHALL encrypt OAuth access tokens and refresh tokens using AES-256 before storing them in the database
4. WHEN a protected API endpoint is called, THE Auth_Service SHALL validate the JWT signature, expiry, and user existence before processing the request
5. IF a user's access token has expired, THEN THE Auth_Service SHALL automatically attempt to refresh it using the stored refresh token before retrying the original request
6. IF a token refresh fails due to a revoked token, THEN THE Auth_Service SHALL return HTTP 401 with `{"error": "reauth_required"}` to the frontend
7. WHEN a user revokes their session, THE Auth_Service SHALL invalidate the stored tokens and terminate the session
8. THE Auth_Service SHALL never include OAuth access tokens or refresh tokens in any API response body

---

### Requirement 2: Dashboard

**User Story:** As a user, I want a unified dashboard, so that I can see my priority emails, pending AI drafts, follow-up count, and productivity stats in one place.

#### Acceptance Criteria

1. WHEN a user loads the dashboard, THE Task_Orchestrator SHALL return a payload containing: priority emails (classified as urgent or normal), pending reply drafts, suggested actions, follow-up count, and analytics stats
2. WHEN one or more backend services are unavailable during a dashboard load, THE Task_Orchestrator SHALL return the data available from the remaining services rather than failing the entire request
3. THE Dashboard SHALL display the follow-up count as a numeric value prominently visible to the user
4. WHEN the dashboard is loaded, THE Task_Orchestrator SHALL fetch emails, analytics, and the daily brief concurrently rather than sequentially

---

### Requirement 3: Email Classification

**User Story:** As a user, I want my incoming emails automatically classified by urgency, so that I can focus on what matters most without manually triaging my inbox.

#### Acceptance Criteria

1. WHEN an email is processed by the Decision_Engine, THE Decision_Engine SHALL assign it a classification of exactly one of: `urgent`, `normal`, or `low`
2. WHEN an email is processed by the Decision_Engine, THE Decision_Engine SHALL assign it a category of exactly one of: `meeting-request`, `action-required`, `info`, or `other`
3. WHEN an email is classified, THE Decision_Engine SHALL log the token usage for that classification call to the Analytics_Service
4. WHEN an email is classified, THE Email_Service SHALL persist the classification and category to the `emails` table in PostgreSQL
5. IF the OpenAI API returns a rate limit error during classification, THEN THE Decision_Engine SHALL retry with exponential backoff (2s, 4s, 8s) for up to 3 attempts
6. IF all classification retries are exhausted, THEN THE Decision_Engine SHALL assign the email a default classification of `normal`

---

### Requirement 4: AI Reply Generation

**User Story:** As a user, I want the platform to generate email replies in my writing style, so that I can respond to emails quickly without composing from scratch.

#### Acceptance Criteria

1. WHEN a user requests a reply for an email, THE Decision_Engine SHALL generate a reply draft that matches the tone specified in the user's preferences (`formal` or `casual`)
2. WHEN generating a reply, THE Email_Service SHALL query FAISS for up to 5 semantically similar past emails to provide style context to the Decision_Engine
3. WHEN a reply draft is generated, THE Email_Service SHALL persist it to the `reply_drafts` table with `status = "pending"`
4. WHILE the execution mode is `suggest` or `approval`, THE Email_Service SHALL NOT send any reply draft to Gmail without explicit user confirmation
5. WHEN the execution mode is `auto` and a reply draft is generated, THE Email_Service SHALL immediately send the draft via Gmail and update its status to `sent`
6. WHEN a reply is sent, THE Analytics_Service SHALL record a `reply_sent` event with `time_saved_min = 5`
7. IF the OpenAI API returns a rate limit error during reply generation, THEN THE Decision_Engine SHALL retry with exponential backoff (2s, 4s, 8s) for up to 3 attempts
8. IF all reply generation retries are exhausted, THEN THE Decision_Engine SHALL return an error response so the user can retry manually
9. WHEN a user edits an AI-generated draft, THE Behavior_Engine SHALL record the edit action to improve future style matching

---

### Requirement 5: Email Embedding and Semantic Search

**User Story:** As a user, I want the platform to learn from my past emails, so that AI-generated replies increasingly match my personal writing style over time.

#### Acceptance Criteria

1. WHEN an email is processed, THE Email_Service SHALL generate an OpenAI embedding of exactly 1536 dimensions using the `text-embedding-3-small` model and store it in the FAISS index
2. WHEN an email is embedded, THE Email_Service SHALL update the `emails.embedding_id` field in PostgreSQL with the FAISS vector ID
3. WHEN the same email is embedded a second time, THE Email_Service SHALL update the existing FAISS vector rather than creating a duplicate entry
4. IF a user has no email history and the FAISS index does not exist, THEN THE Email_Service SHALL initialize an empty FAISS index and proceed with tone-only reply generation

---

### Requirement 6: Calendar Free Slot Detection

**User Story:** As a user, I want the platform to identify available meeting times from my calendar, so that I can respond to meeting requests with accurate availability.

#### Acceptance Criteria

1. WHEN free slots are requested, THE Calendar_Service SHALL return only time slots that fall within the user's configured working hours start and end times
2. WHEN free slots are requested, THE Calendar_Service SHALL return only time slots that fall on the user's configured working days
3. WHEN free slots are requested, THE Calendar_Service SHALL return only time slots that do not overlap with any existing calendar event
4. WHEN free slots are requested, THE Calendar_Service SHALL return slots sorted in ascending order by start time
5. WHEN free slots are requested, THE Calendar_Service SHALL return slots where each slot duration equals the user's configured `meeting_duration` in minutes
6. WHEN a meeting request email is detected, THE Calendar_Service SHALL query the next 7 days for free slots and pass them to the Decision_Engine for AI-ranked suggestions
7. WHEN meeting slot suggestions are returned to the user, THE Calendar_Service SHALL return at most 3 ranked suggestions
8. WHEN a user confirms a meeting slot, THE Calendar_Service SHALL create a calendar event in Google Calendar with the correct attendees from the source email
9. IF the Google Calendar API is unavailable, THEN THE Calendar_Service SHALL return mock free slots based on the user's working hours preferences and flag the response with `{"source": "mock", "reason": "calendar_unavailable"}`

---

### Requirement 7: Follow-up Agent

**User Story:** As a user, I want the platform to detect emails I sent that haven't received a reply, so that I never miss an important follow-up.

#### Acceptance Criteria

1. WHEN the follow-up check runs, THE Followup_Agent SHALL return only emails where the sent time is older than the user's configured `followup_threshold` days AND `is_replied` is `false`
2. WHEN the follow-up check runs, THE Followup_Agent SHALL exclude any email that already has a follow-up record with status `snoozed`, `resolved`, or `sent`
3. THE Followup_Agent SHALL ensure that at most one follow-up record with `status = "pending"` exists per email at any time
4. WHEN follow-up suggestions are returned, THE Followup_Agent SHALL sort them by `sent_at` ascending (oldest first)
5. WHEN a follow-up is detected, THE Decision_Engine SHALL generate a contextual follow-up draft for that email
6. WHEN a user snoozes a follow-up, THE Followup_Agent SHALL suppress that follow-up from results until the specified snooze datetime has passed
7. WHEN a user marks a follow-up as resolved, THE Followup_Agent SHALL update its status to `resolved` and exclude it from future follow-up checks

---

### Requirement 8: Daily AI Brief

**User Story:** As a user, I want a daily AI-generated summary of my most important items, so that I can start my day with a clear picture of what needs attention.

#### Acceptance Criteria

1. WHEN a daily brief is generated, THE Decision_Engine SHALL produce a brief containing exactly 3 urgent items
2. WHEN a daily brief is generated, THE Decision_Engine SHALL produce a brief containing exactly 2 follow-up items
3. WHEN a daily brief is generated, THE Decision_Engine SHALL produce a brief containing exactly 1 non-empty risk description
4. WHEN generating a daily brief, THE Task_Orchestrator SHALL gather context from: urgent emails, pending follow-ups, upcoming calendar events (next 2 days), and current analytics stats

---

### Requirement 9: Behavior Engine and User Preferences

**User Story:** As a user, I want to configure my communication style and working preferences, so that the AI acts as a faithful representation of how I work.

#### Acceptance Criteria

1. THE Behavior_Engine SHALL persist each user's tone preference (`formal` or `casual`), working hours start and end times, working days, meeting duration, follow-up threshold, and execution mode
2. WHEN a user updates their preferences, THE Behavior_Engine SHALL store the updated values and apply them to all subsequent AI operations
3. WHEN building a reply prompt, THE Behavior_Engine SHALL provide a StyleContext containing the user's tone and semantically similar past email examples retrieved from FAISS
4. WHEN a user's preferences are requested, THE Behavior_Engine SHALL return the stored values without modification

---

### Requirement 10: Execution Mode Control

**User Story:** As a user, I want to control how autonomously the AI acts on my behalf, so that I can trust the system with the right level of automation for my comfort.

#### Acceptance Criteria

1. WHILE the execution mode is `suggest`, THE Task_Orchestrator SHALL present all AI-generated actions as suggestions and SHALL NOT execute any action without explicit user confirmation
2. WHILE the execution mode is `approval`, THE Task_Orchestrator SHALL require explicit user approval before sending any reply, creating any calendar event, or sending any follow-up
3. WHILE the execution mode is `auto`, THE Task_Orchestrator SHALL execute all generated actions immediately after generation without requiring user confirmation
4. WHEN the execution mode is changed by the user, THE Behavior_Engine SHALL persist the new mode and apply it to all subsequent actions immediately

---

### Requirement 11: Analytics and Productivity Tracking

**User Story:** As a user, I want to see metrics on how much the AI has automated for me, so that I can understand the value the platform is delivering.

#### Acceptance Criteria

1. WHEN an automated action completes (reply sent, calendar event created, or follow-up sent), THE Analytics_Service SHALL record an analytics event of the corresponding type
2. THE Analytics_Service SHALL compute `actions_automated` as the sum of `reply_sent` + `event_created` + `followup_sent` event counts for the requested period
3. WHEN computing time saved, THE Analytics_Service SHALL use the configured constants: 5 minutes per reply sent and 10 minutes per calendar event created
4. WHEN dashboard stats are requested, THE Analytics_Service SHALL return `actions_automated`, `time_saved_minutes`, `emails_classified`, `replies_sent`, and `events_created` for the requested period

---

### Requirement 12: Security and Input Safety

**User Story:** As a user, I want my data and credentials to be handled securely, so that my Google account and personal communications are protected.

#### Acceptance Criteria

1. THE Auth_Service SHALL store OAuth access tokens and refresh tokens encrypted at rest using AES-256; the encryption key SHALL be loaded from environment variables and never hardcoded
2. THE Platform SHALL never include OAuth tokens in any API response body
3. WHEN email body text is injected into an LLM prompt, THE Decision_Engine SHALL sanitize the input to prevent prompt injection attacks
4. THE Platform SHALL enforce a rate limit of 30 requests per minute per user on the `/emails/generate-reply` and `/calendar/suggest` endpoints
5. WHEN running in production, THE Platform SHALL restrict CORS to the configured frontend domain only
6. THE Auth_Service SHALL request only the minimum required Google OAuth scopes: `gmail.readonly`, `gmail.send`, `calendar.readonly`, and `calendar.events`

---

### Requirement 13: Error Handling and Resilience

**User Story:** As a user, I want the platform to handle external service failures gracefully, so that temporary outages do not break my workflow.

#### Acceptance Criteria

1. IF the Gmail API returns a 401 error due to an expired token, THEN THE Auth_Service SHALL automatically refresh the token and retry the original request once
2. IF the Gmail API is unavailable, THEN THE Email_Service SHALL fall back to mock email data and continue serving the dashboard
3. IF the Google Calendar API is unavailable, THEN THE Calendar_Service SHALL return mock free slots based on the user's working hours preferences
4. IF the FAISS index does not exist for a user, THEN THE Email_Service SHALL initialize an empty index and proceed with tone-only context for reply generation
5. IF the PostgreSQL database is unreachable, THEN THE Platform SHALL return HTTP 503 with `{"error": "service_temporarily_unavailable"}` and SHALL NOT expose internal database details in the response
6. IF the OpenAI API returns a rate limit error, THEN THE Decision_Engine SHALL retry with exponential backoff: 2 seconds, 4 seconds, then 8 seconds, for a maximum of 3 attempts

---

### Requirement 14: File Brain (Demo)

**User Story:** As a user, I want to see a demonstration of AI-powered file organization, so that I can understand the platform's potential for automating file management tasks.

#### Acceptance Criteria

1. WHEN the File Brain feature is accessed, THE Platform SHALL display a simulated file organization interface using mock data
2. WHEN a file organization action is triggered in demo mode, THE Platform SHALL simulate AI-based file renaming and categorization without modifying any real files

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Classification Completeness

*For any* email with a non-empty body processed by the Decision_Engine, the resulting classification must be exactly one of `"urgent"`, `"normal"`, or `"low"` — no email is left unclassified or assigned an out-of-vocabulary label.

**Validates: Requirements 3.1**

---

### Property 2: Draft Immutability Before Approval

*For any* ReplyDraft with `status = "pending"` and any execution mode that is not `"auto"`, the draft must never be transmitted to Gmail. Only drafts explicitly approved by the user (in `approval` mode) or generated in `auto` mode may be sent.

**Validates: Requirements 4.3, 4.4, 4.5, 10.1, 10.2**

---

### Property 3: Free Slot Validity

*For any* user preferences and date range, every TimeSlot returned by `get_free_slots` must satisfy: `slot.start.time() ≥ working_hours_start`, `slot.end.time() ≤ working_hours_end`, `slot.start.isoweekday() ∈ working_days`, and the slot must not overlap with any existing calendar event.

**Validates: Requirements 6.1, 6.2, 6.3**

---

### Property 4: Follow-up Non-Duplication

*For any* email, at most one follow-up record with `status = "pending"` exists at any point in time. Resolved, snoozed, or sent follow-ups are never re-surfaced as new pending items.

**Validates: Requirements 7.2, 7.3**

---

### Property 5: Analytics Consistency

*For any* user and time period, `analytics.actions_automated` must equal `COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)` — the aggregate count always equals the sum of individual event type counts.

**Validates: Requirements 11.1, 11.2**

---

### Property 6: Token Security

*For any* API response returned by the Platform, the response body must not contain any OAuth access token or refresh token value.

**Validates: Requirements 1.8, 12.2**

---

### Property 7: Daily Brief Structure

*For any* context provided to the brief generator, the resulting DailyBrief must contain exactly 3 urgent items, exactly 2 follow-up items, and exactly 1 non-empty risk string.

**Validates: Requirements 8.1, 8.2, 8.3**

---

### Property 8: Execution Mode Enforcement

*For any* generated action (reply, calendar event, follow-up) and any execution mode, the action must only be executed automatically if and only if the execution mode is `"auto"`. In `"suggest"` or `"approval"` mode, no action executes without explicit user confirmation.

**Validates: Requirements 10.1, 10.2, 10.3**
