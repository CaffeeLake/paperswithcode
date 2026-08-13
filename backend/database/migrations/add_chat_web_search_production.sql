BEGIN;

-- Production counterpart to add_chat_web_search.sql. Keep the compatibility
-- schema in public even while production web search remains disabled.
SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_web_search_production.sql must run in public';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        RAISE EXCEPTION
            'paperswithcode_user must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS web_search_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS web_search_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS web_search_calls INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS web_search_failed BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS chat_web_search_budget_states (
    id UUID PRIMARY KEY,
    environment VARCHAR(32) NOT NULL,
    billing_cycle DATE NOT NULL,
    cycle_end_at TIMESTAMPTZ NOT NULL,
    warning_calls INTEGER NOT NULL,
    hard_limit_calls INTEGER NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    provider_cost_microusd BIGINT NOT NULL DEFAULT 0,
    last_latency_ms INTEGER,
    last_result_count INTEGER,
    circuit_state VARCHAR(16) NOT NULL DEFAULT 'armed'
        CHECK (circuit_state IN ('armed','warning','cooldown','tripped')),
    trip_reason VARCHAR(64),
    cooldown_until TIMESTAMPTZ,
    last_provider_error_class VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (environment, billing_cycle),
    CHECK (call_count >= 0 AND success_count >= 0 AND failure_count >= 0
        AND provider_cost_microusd >= 0 AND warning_calls > 0
        AND hard_limit_calls >= warning_calls)
);

CREATE TABLE IF NOT EXISTS chat_web_search_circuit_events (
    id UUID PRIMARY KEY,
    budget_state_id UUID NOT NULL
        REFERENCES chat_web_search_budget_states(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    error_class VARCHAR(64),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_web_search_events_recent
    ON chat_web_search_circuit_events (budget_state_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_web_search_owner_usage (
    environment VARCHAR(32) NOT NULL,
    billing_cycle DATE NOT NULL,
    owner_hash VARCHAR(64) NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (environment, billing_cycle, owner_hash),
    CHECK (call_count >= 0)
);

ALTER TABLE chat_web_search_budget_states OWNER TO paperswithcode_user;
ALTER TABLE chat_web_search_circuit_events OWNER TO paperswithcode_user;
ALTER TABLE chat_web_search_owner_usage OWNER TO paperswithcode_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    chat_web_search_budget_states,
    chat_web_search_circuit_events,
    chat_web_search_owner_usage
TO paperswithcode_user;
GRANT SELECT, UPDATE (web_search_enabled) ON chat_sessions TO paperswithcode_user;
GRANT SELECT, UPDATE (web_search_enabled) ON chat_messages TO paperswithcode_user;
GRANT SELECT, UPDATE (web_search_calls, web_search_failed)
    ON chat_turn_capabilities TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        REVOKE ALL ON
            chat_web_search_budget_states,
            chat_web_search_circuit_events,
            chat_web_search_owner_usage
        FROM pwc_staging;
        REVOKE UPDATE (web_search_enabled) ON chat_sessions FROM pwc_staging;
        REVOKE UPDATE (web_search_enabled) ON chat_messages FROM pwc_staging;
        REVOKE UPDATE (web_search_calls, web_search_failed)
            ON chat_turn_capabilities FROM pwc_staging;
    END IF;
END $$;

COMMIT;
