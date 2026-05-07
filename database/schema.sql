-- Users and authentication
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    picture_url TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE oauth_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    access_token    TEXT NOT NULL,          -- encrypted at rest
    refresh_token   TEXT NOT NULL,          -- encrypted at rest
    token_expiry    TIMESTAMPTZ NOT NULL,
    scopes          TEXT[] NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- User behavioral preferences
CREATE TABLE user_preferences (
    user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    tone                TEXT NOT NULL DEFAULT 'casual',   -- 'formal' | 'casual'
    working_hours_start TIME NOT NULL DEFAULT '09:00',
    working_hours_end   TIME NOT NULL DEFAULT '18:00',
    working_days        INT[] NOT NULL DEFAULT '{1,2,3,4,5}', -- 1=Mon
    meeting_duration    INT NOT NULL DEFAULT 30,           -- minutes
    followup_threshold  INT NOT NULL DEFAULT 3,            -- days
    execution_mode      TEXT NOT NULL DEFAULT 'suggest',   -- 'suggest' | 'approval' | 'auto'
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Emails
CREATE TABLE emails (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    gmail_id        TEXT NOT NULL,
    thread_id       TEXT NOT NULL,
    subject         TEXT,
    sender          TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    body_text       TEXT,
    received_at     TIMESTAMPTZ NOT NULL,
    classification  TEXT,                  -- 'urgent' | 'normal' | 'low'
    category        TEXT,                  -- 'meeting-request' | 'action-required' | 'info' | 'other'
    is_replied      BOOLEAN DEFAULT FALSE,
    embedding_id    TEXT,                  -- FAISS vector ID
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, gmail_id)
);

-- AI-generated reply drafts
CREATE TABLE reply_drafts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    email_id    UUID REFERENCES emails(id) ON DELETE CASCADE,
    draft_text  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'sent' | 'discarded'
    sent_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Calendar events
CREATE TABLE calendar_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    gcal_event_id   TEXT,
    title           TEXT NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    attendees       TEXT[],
    source_email_id UUID REFERENCES emails(id),
    created_by_ai   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Follow-up tracking
CREATE TABLE followups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    email_id        UUID REFERENCES emails(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'snoozed' | 'resolved' | 'sent'
    snooze_until    TIMESTAMPTZ,
    draft_id        UUID REFERENCES reply_drafts(id),
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

-- Analytics events
CREATE TABLE analytics_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,   -- 'reply_sent' | 'event_created' | 'followup_triggered' | 'email_classified'
    metadata        JSONB,
    time_saved_min  FLOAT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_emails_user_received ON emails(user_id, received_at DESC);
CREATE INDEX idx_emails_classification ON emails(user_id, classification);
CREATE INDEX idx_followups_user_status ON followups(user_id, status);
CREATE INDEX idx_analytics_user_created ON analytics_events(user_id, created_at DESC);
