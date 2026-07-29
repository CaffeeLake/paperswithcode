BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_sandbox_pool.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (
           SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner'
       ) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_sandbox_pool (
    id UUID PRIMARY KEY,
    modal_sandbox_id VARCHAR(255) UNIQUE,
    state VARCHAR(24) NOT NULL DEFAULT 'starting'
        CHECK (
            state IN (
                'starting',
                'blank_ready',
                'claimed',
                'draining',
                'terminated',
                'failed'
            )
        ),
    image_version VARCHAR(255) NOT NULL,
    worker_contract_version VARCHAR(64) NOT NULL,
    worker_generation VARCHAR(64) NOT NULL,
    app_release_id VARCHAR(255) NOT NULL,
    claim_generation INTEGER NOT NULL DEFAULT 0,
    claim_token_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ready_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    cpu_request NUMERIC(8, 3) NOT NULL,
    cpu_limit NUMERIC(8, 3) NOT NULL,
    memory_request_mib INTEGER NOT NULL,
    memory_limit_mib INTEGER NOT NULL,
    blank_billable_seconds BIGINT NOT NULL DEFAULT 0,
    estimated_blank_cost_usd NUMERIC(14, 6) NOT NULL DEFAULT 0,
    billing_month DATE NOT NULL,
    failure_code VARCHAR(64),
    last_health_checked_at TIMESTAMPTZ,
    CONSTRAINT chat_sandbox_pool_cpu_check
        CHECK (cpu_request > 0 AND cpu_limit >= cpu_request),
    CONSTRAINT chat_sandbox_pool_memory_check
        CHECK (
            memory_request_mib > 0
            AND memory_limit_mib >= memory_request_mib
        )
);

ALTER TABLE chat_sandbox_leases
    ADD COLUMN IF NOT EXISTS worker_generation VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_chat_sandbox_pool_claim
    ON chat_sandbox_pool (
        state,
        image_version,
        worker_contract_version,
        app_release_id,
        expires_at,
        ready_at
    );
CREATE INDEX IF NOT EXISTS idx_chat_sandbox_pool_billing
    ON chat_sandbox_pool (billing_month, state);

ALTER TABLE chat_sandbox_pool OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO pwc_staging;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        REVOKE ALL ON chat_sandbox_pool FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
