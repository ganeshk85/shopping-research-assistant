-- v2 schema (Sprint 6, US-24 / US-26). Every owned row belongs to a user.
-- Prices are DOUBLE PRECISION in the listing currency (the v1 rules, on Postgres).

CREATE TABLE users (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username     TEXT        NOT NULL UNIQUE,
    display_name TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The single user used until sign-in exists (BL-01). The API resolves the current
-- user to this row; nothing else depends on its id. Renamed to 'admin' by 0002.
INSERT INTO users (username, display_name) VALUES ('owner', 'Owner');

CREATE TABLE tracked_items (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id              BIGINT           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_name         TEXT             NOT NULL,
    retailer             TEXT             NOT NULL,
    url                  TEXT             NOT NULL,
    currency             TEXT             NOT NULL DEFAULT 'CAD',
    initial_price        DOUBLE PRECISION NOT NULL CHECK (initial_price >= 0),
    target_price         DOUBLE PRECISION NOT NULL CHECK (target_price > 0),
    lowest_price_seen    DOUBLE PRECISION NOT NULL,
    last_notified_price  DOUBLE PRECISION,
    status               TEXT             NOT NULL DEFAULT 'active'
                                          CHECK (status IN ('active', 'paused')),
    created_at           TIMESTAMPTZ      NOT NULL DEFAULT now(),
    -- Monitor health: last attempt (success or failure) and the failure streak.
    last_check_at        TIMESTAMPTZ,
    last_check_error     TEXT,
    consecutive_failures INTEGER          NOT NULL DEFAULT 0,
    -- A user tracks each product page once; other users may track the same page.
    UNIQUE (user_id, url)
);

CREATE INDEX idx_tracked_items_user_status ON tracked_items (user_id, status);

-- Owned through its item: queries join tracked_items to check the user.
CREATE TABLE price_history (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id    BIGINT           NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
    price      DOUBLE PRECISION NOT NULL,
    in_stock   BOOLEAN          NOT NULL,
    checked_at TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_price_history_item ON price_history (item_id, checked_at);

-- Registry of research conversations (US-03). The messages live in the LangGraph
-- checkpoint tables (PostgresSaver); this table lists threads and records the owner.
CREATE TABLE research_threads (
    thread_id         TEXT        PRIMARY KEY,
    user_id           BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title             TEXT        NOT NULL,
    finalized_product TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_research_threads_user_updated ON research_threads (user_id, updated_at DESC);
