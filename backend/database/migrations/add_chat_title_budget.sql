BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_title_budget.sql must run with search_path staging,public or public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_title_budget_states (
    id UUID PRIMARY KEY,
    environment VARCHAR(32) NOT NULL,
    billing_cycle DATE NOT NULL,
    cycle_end_at TIMESTAMPTZ NOT NULL,
    warning_microusd BIGINT NOT NULL,
    application_cap_microusd BIGINT NOT NULL,
    spent_microusd BIGINT NOT NULL DEFAULT 0,
    reserved_microusd BIGINT NOT NULL DEFAULT 0,
    circuit_state VARCHAR(16) NOT NULL DEFAULT 'armed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chat_title_budget_cycle UNIQUE (environment, billing_cycle),
    CONSTRAINT chat_title_budget_state_check CHECK (
        spent_microusd >= 0 AND reserved_microusd >= 0
        AND circuit_state IN ('armed','warning','tripped')
    )
);

CREATE TABLE IF NOT EXISTS chat_title_provider_calls (
    id UUID PRIMARY KEY,
    budget_state_id UUID NOT NULL REFERENCES chat_title_budget_states(id),
    environment VARCHAR(32) NOT NULL,
    billing_cycle DATE NOT NULL,
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    state VARCHAR(24) NOT NULL,
    reserved_microusd BIGINT NOT NULL,
    actual_microusd BIGINT,
    input_tokens BIGINT,
    output_tokens BIGINT,
    provider_generation_id TEXT,
    reserved_at TIMESTAMPTZ NOT NULL,
    dispatched_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_title_provider_calls_state_check CHECK (
        state IN ('reserved','dispatched','settled','released')
    ),
    CONSTRAINT chat_title_provider_calls_nonnegative_check CHECK (
        reserved_microusd >= 0
        AND (actual_microusd IS NULL OR actual_microusd >= 0)
        AND (input_tokens IS NULL OR input_tokens >= 0)
        AND (output_tokens IS NULL OR output_tokens >= 0)
    )
);
CREATE INDEX IF NOT EXISTS idx_chat_title_calls_cycle
    ON chat_title_provider_calls (environment, billing_cycle, state);

CREATE TABLE IF NOT EXISTS chat_title_budget_events (
    id UUID PRIMARY KEY,
    budget_state_id UUID NOT NULL REFERENCES chat_title_budget_states(id),
    event_type VARCHAR(32) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    delivery_state VARCHAR(24) NOT NULL DEFAULT 'pending',
    fallback_delivery_state VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chat_title_budget_event UNIQUE (budget_state_id, event_type)
);
CREATE INDEX IF NOT EXISTS idx_chat_title_budget_events_delivery
    ON chat_title_budget_events (delivery_state, created_at);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
           OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
            RAISE EXCEPTION 'staging chat title migration requires staging roles';
        END IF;
        ALTER TABLE chat_title_budget_states OWNER TO pwc_staging_owner;
        ALTER TABLE chat_title_provider_calls OWNER TO pwc_staging_owner;
        ALTER TABLE chat_title_budget_events OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE ON
            chat_title_budget_states,
            chat_title_provider_calls,
            chat_title_budget_events TO pwc_staging;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
            REVOKE ALL ON
                chat_title_budget_states,
                chat_title_provider_calls,
                chat_title_budget_events FROM paperswithcode_user;
        END IF;
    ELSE
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
            RAISE EXCEPTION 'production chat title migration requires paperswithcode_user';
        END IF;
        ALTER TABLE chat_title_budget_states OWNER TO paperswithcode_user;
        ALTER TABLE chat_title_provider_calls OWNER TO paperswithcode_user;
        ALTER TABLE chat_title_budget_events OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE ON
            chat_title_budget_states,
            chat_title_provider_calls,
            chat_title_budget_events TO paperswithcode_user;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
            REVOKE ALL ON
                chat_title_budget_states,
                chat_title_provider_calls,
                chat_title_budget_events FROM pwc_staging;
        END IF;
    END IF;
END $$;

COMMIT;
