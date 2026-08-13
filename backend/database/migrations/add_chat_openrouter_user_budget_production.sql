BEGIN;

-- Production counterpart to add_chat_openrouter_user_budget.sql. Keep every
-- object in public and explicitly deny the staging runtime role.
SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_openrouter_user_budget_production.sql must run in public';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        RAISE EXCEPTION
            'paperswithcode_user must exist before this migration';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_openrouter_credentials (
    hf_user_id VARCHAR(255) PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL CHECK (octet_length(nonce) = 12),
    encryption_key_version INTEGER NOT NULL CHECK (encryption_key_version > 0),
    verified_at TIMESTAMPTZ NOT NULL,
    fallback_enabled BOOLEAN NOT NULL DEFAULT false,
    credential_revision UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_openrouter_monthly_usage (
    hf_user_id VARCHAR(255) NOT NULL,
    month_start DATE NOT NULL,
    limit_microusd BIGINT NOT NULL,
    reserved_microusd BIGINT NOT NULL DEFAULT 0,
    spent_microusd BIGINT NOT NULL DEFAULT 0,
    unknown_cost_calls INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (hf_user_id, month_start),
    CONSTRAINT chat_openrouter_monthly_usage_nonnegative_check CHECK (
        limit_microusd > 0 AND reserved_microusd >= 0
        AND spent_microusd >= 0 AND unknown_cost_calls >= 0
    )
);

CREATE TABLE IF NOT EXISTS chat_openrouter_provider_calls (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL,
    call_sequence INTEGER NOT NULL CHECK (call_sequence >= 1),
    hf_user_id VARCHAR(255) NOT NULL,
    month_start DATE NOT NULL,
    model_route VARCHAR(255) NOT NULL,
    state VARCHAR(24) NOT NULL,
    reserved_microusd BIGINT NOT NULL,
    actual_microusd BIGINT,
    generation_id TEXT,
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_openrouter_provider_calls_state_check CHECK (
        state IN ('reserved','dispatched','settled','released','cost_unknown')
    ),
    CONSTRAINT chat_openrouter_provider_calls_nonnegative_check CHECK (
        reserved_microusd >= 0 AND (actual_microusd IS NULL OR actual_microusd >= 0)
    ),
    CONSTRAINT uq_chat_openrouter_turn_call UNIQUE (turn_id, call_sequence),
    FOREIGN KEY (hf_user_id, month_start)
        REFERENCES chat_openrouter_monthly_usage (hf_user_id, month_start)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_chat_openrouter_calls_owner_month
    ON chat_openrouter_provider_calls (hf_user_id, month_start);
CREATE INDEX IF NOT EXISTS idx_chat_openrouter_calls_state_updated
    ON chat_openrouter_provider_calls (state, updated_at);

CREATE TABLE IF NOT EXISTS chat_openrouter_credential_audit (
    id BIGSERIAL PRIMARY KEY,
    owner_hash VARCHAR(64) NOT NULL,
    action VARCHAR(32) NOT NULL CHECK (
        action IN ('connected','replaced','fallback_enabled','fallback_disabled',
                   'disconnected','invalidated','account_deleted')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_openrouter_credential_audit_created
    ON chat_openrouter_credential_audit (created_at);

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS provider_mode VARCHAR(32),
    ADD COLUMN IF NOT EXISTS provider_credential_revision UUID,
    ADD COLUMN IF NOT EXISTS provider_error_code VARCHAR(64);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_turn_capabilities'::regclass
          AND conname = 'chat_turn_capabilities_provider_mode_check'
    ) THEN
        ALTER TABLE chat_turn_capabilities
            ADD CONSTRAINT chat_turn_capabilities_provider_mode_check CHECK (
                provider_mode IS NULL OR provider_mode IN
                ('huggingface','openrouter_funded','openrouter_byok')
            );
    END IF;
END $$;

ALTER TABLE chat_openrouter_credentials OWNER TO paperswithcode_user;
ALTER TABLE chat_openrouter_monthly_usage OWNER TO paperswithcode_user;
ALTER TABLE chat_openrouter_provider_calls OWNER TO paperswithcode_user;
ALTER TABLE chat_openrouter_credential_audit OWNER TO paperswithcode_user;
ALTER SEQUENCE chat_openrouter_credential_audit_id_seq OWNER TO paperswithcode_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    chat_openrouter_credentials,
    chat_openrouter_monthly_usage,
    chat_openrouter_provider_calls,
    chat_openrouter_credential_audit TO paperswithcode_user;
GRANT USAGE, SELECT ON SEQUENCE chat_openrouter_credential_audit_id_seq
    TO paperswithcode_user;
GRANT SELECT, UPDATE (provider_mode, provider_credential_revision, provider_error_code)
    ON chat_turn_capabilities TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        REVOKE ALL ON chat_openrouter_credentials,
            chat_openrouter_monthly_usage,
            chat_openrouter_provider_calls,
            chat_openrouter_credential_audit FROM pwc_staging;
        REVOKE ALL ON SEQUENCE chat_openrouter_credential_audit_id_seq
            FROM pwc_staging;
    END IF;
END $$;

COMMIT;
