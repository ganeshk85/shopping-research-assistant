-- Sprint 8 (US-32, US-34, US-35): recorded price-check runs, the background worker's
-- schedule, and per-user notification settings.

-- One row per price check, whoever started it. Counts are filled in when it ends.
CREATE TABLE monitor_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger       TEXT        NOT NULL CHECK (trigger IN ('schedule', 'api', 'cli')),
    status        TEXT        NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running', 'finished', 'failed')),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    active_items  INTEGER,
    checked       INTEGER,
    failed        INTEGER,
    alerts_sent   INTEGER,
    alerts_failed INTEGER,   -- not delivered; retried at the next check
    error         TEXT       -- why the whole run failed (status = 'failed')
);

CREATE INDEX idx_monitor_runs_user_started ON monitor_runs (user_id, started_at DESC);

-- The background worker's heartbeat and schedule, so the API can say when the next
-- check is due. Process-level, not owned by a user.
CREATE TABLE worker_status (
    name           TEXT        PRIMARY KEY,
    pid            INTEGER     NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    heartbeat_at   TIMESTAMPTZ NOT NULL,
    interval_hours INTEGER     NOT NULL,
    next_run_at    TIMESTAMPTZ,
    stopped_at     TIMESTAMPTZ
);

-- A user's alert channel. No row = use the NOTIFIER settings in .env (v1 behaviour).
-- Server secrets (Resend key, SMTP login, the sender address) stay in .env.
CREATE TABLE notification_settings (
    user_id     BIGINT      PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    channel     TEXT        NOT NULL CHECK (channel IN ('console', 'webhook', 'email')),
    webhook_url TEXT,
    alert_email TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
