DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION 'add_chat_web_search.sql must run with search_path staging,public';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS web_search_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS web_search_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS web_search_calls integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS web_search_failed boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS chat_web_search_budget_states (
    id uuid PRIMARY KEY,
    environment varchar(32) NOT NULL,
    billing_cycle date NOT NULL,
    cycle_end_at timestamptz NOT NULL,
    warning_calls integer NOT NULL,
    hard_limit_calls integer NOT NULL,
    call_count integer NOT NULL DEFAULT 0,
    success_count integer NOT NULL DEFAULT 0,
    failure_count integer NOT NULL DEFAULT 0,
    provider_cost_microusd bigint NOT NULL DEFAULT 0,
    last_latency_ms integer,
    last_result_count integer,
    circuit_state varchar(16) NOT NULL DEFAULT 'armed'
        CHECK (circuit_state IN ('armed','warning','cooldown','tripped')),
    trip_reason varchar(64),
    cooldown_until timestamptz,
    last_provider_error_class varchar(64),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (environment, billing_cycle),
    CHECK (call_count >= 0 AND success_count >= 0 AND failure_count >= 0
        AND provider_cost_microusd >= 0 AND warning_calls > 0
        AND hard_limit_calls >= warning_calls)
);

CREATE TABLE IF NOT EXISTS chat_web_search_circuit_events (
    id uuid PRIMARY KEY,
    budget_state_id uuid NOT NULL REFERENCES chat_web_search_budget_states(id) ON DELETE CASCADE,
    event_type varchar(64) NOT NULL,
    error_class varchar(64),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_web_search_events_recent
    ON chat_web_search_circuit_events (budget_state_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_web_search_owner_usage (
    environment varchar(32) NOT NULL,
    billing_cycle date NOT NULL,
    owner_hash varchar(64) NOT NULL,
    call_count integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (environment, billing_cycle, owner_hash),
    CHECK (call_count >= 0)
);

ALTER TABLE chat_web_search_budget_states OWNER TO pwc_staging_owner;
ALTER TABLE chat_web_search_circuit_events OWNER TO pwc_staging_owner;
ALTER TABLE chat_web_search_owner_usage OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE ON
    chat_web_search_budget_states,
    chat_web_search_circuit_events,
    chat_web_search_owner_usage
TO pwc_staging;
REVOKE ALL ON
    chat_web_search_budget_states,
    chat_web_search_circuit_events,
    chat_web_search_owner_usage
FROM paperswithcode_user;
