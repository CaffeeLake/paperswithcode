BEGIN;

SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_direct_openai_production.sql must run with search_path public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        RAISE EXCEPTION
            'production and staging application roles must exist before this migration';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_openai_monthly_usage (
    owner_id VARCHAR(255) NOT NULL,
    month_start DATE NOT NULL,
    limit_microusd BIGINT NOT NULL,
    reserved_microusd BIGINT NOT NULL DEFAULT 0,
    spent_microusd BIGINT NOT NULL DEFAULT 0,
    unknown_cost_calls INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, month_start),
    CONSTRAINT chat_openai_monthly_usage_nonnegative_check CHECK (
        limit_microusd > 0 AND reserved_microusd >= 0
        AND spent_microusd >= 0 AND unknown_cost_calls >= 0
    )
);

CREATE TABLE IF NOT EXISTS chat_openai_provider_calls (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL,
    call_sequence INTEGER NOT NULL CHECK (call_sequence >= 1),
    owner_id VARCHAR(255) NOT NULL,
    environment VARCHAR(32) NOT NULL,
    month_start DATE NOT NULL,
    public_model_id VARCHAR(255) NOT NULL,
    provider_model VARCHAR(255) NOT NULL,
    reasoning_effort VARCHAR(16) NOT NULL CHECK (
        reasoning_effort IN ('low','high','max')
    ),
    service_tier VARCHAR(32) NOT NULL DEFAULT 'default',
    request_bytes INTEGER NOT NULL CHECK (request_bytes > 0),
    input_tokens INTEGER,
    cached_input_tokens INTEGER,
    cache_write_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    response_id VARCHAR(255),
    provider_request_id VARCHAR(255),
    provider_latency_ms INTEGER,
    provider_ttft_ms INTEGER,
    outcome VARCHAR(64),
    error_code VARCHAR(64),
    settlement_source VARCHAR(32) CHECK (
        settlement_source IS NULL OR settlement_source IN
        ('provider_usage','recovered_provider_usage','reserved_ceiling')
    ),
    state VARCHAR(24) NOT NULL CHECK (
        state IN ('reserved','dispatched','settled','released','cost_unknown')
    ),
    reserved_microusd BIGINT NOT NULL CHECK (reserved_microusd >= 0),
    actual_microusd BIGINT CHECK (actual_microusd >= 0),
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chat_openai_turn_call UNIQUE (turn_id, call_sequence),
    FOREIGN KEY (owner_id, month_start)
        REFERENCES chat_openai_monthly_usage (owner_id, month_start)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_chat_openai_calls_owner_month
    ON chat_openai_provider_calls (owner_id, month_start);
CREATE INDEX IF NOT EXISTS idx_chat_openai_calls_state_updated
    ON chat_openai_provider_calls (state, updated_at);
CREATE INDEX IF NOT EXISTS idx_chat_openai_calls_environment_month
    ON chat_openai_provider_calls (environment, month_start);

ALTER TABLE chat_turn_capabilities
    DROP CONSTRAINT IF EXISTS chat_turn_capabilities_provider_mode_check;
ALTER TABLE chat_turn_capabilities
    ADD CONSTRAINT chat_turn_capabilities_provider_mode_check CHECK (
        provider_mode IS NULL OR provider_mode IN
        ('huggingface','openrouter_funded','openrouter_byok','openai_funded')
    );

ALTER TABLE chat_openai_monthly_usage OWNER TO paperswithcode_user;
ALTER TABLE chat_openai_provider_calls OWNER TO paperswithcode_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    chat_openai_monthly_usage, chat_openai_provider_calls TO paperswithcode_user;
GRANT SELECT, UPDATE (provider_mode, provider_error_code)
    ON chat_turn_capabilities TO paperswithcode_user;

REVOKE ALL ON chat_openai_monthly_usage,
    chat_openai_provider_calls FROM pwc_staging;

COMMIT;
