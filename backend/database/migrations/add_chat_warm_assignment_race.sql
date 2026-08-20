BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_warm_assignment_race.sql requires search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION 'production chat migration requires paperswithcode_user';
    END IF;
END $$;

ALTER TABLE chat_sandbox_pool
    ADD COLUMN IF NOT EXISTS health_check_token_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS health_check_started_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_chat_sandbox_pool_available_health
    ON chat_sandbox_pool (
        state,
        health_check_token_hash,
        expires_at,
        ready_at
    );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_sandbox_pool'::regclass
          AND conname = 'chat_sandbox_pool_health_check_pair_check'
    ) THEN
        ALTER TABLE chat_sandbox_pool
            ADD CONSTRAINT chat_sandbox_pool_health_check_pair_check
            CHECK (
                (health_check_token_hash IS NULL)
                = (health_check_started_at IS NULL)
            );
    END IF;
END $$;

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS failure_stage VARCHAR(32),
    ADD COLUMN IF NOT EXISTS failure_class VARCHAR(128),
    ADD COLUMN IF NOT EXISTS attempt_kind VARCHAR(16),
    ADD COLUMN IF NOT EXISTS retry_overhead_ms INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_turn_latency'::regclass
          AND conname = 'chat_turn_latency_attempt_kind_check'
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_attempt_kind_check
            CHECK (attempt_kind IS NULL OR attempt_kind IN ('pool','reused','direct'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_turn_latency'::regclass
          AND conname = 'chat_turn_latency_retry_overhead_check'
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_retry_overhead_check
            CHECK (retry_overhead_ms IS NULL OR retry_overhead_ms BETWEEN 0 AND 3600000);
    END IF;
END $$;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_sandbox_pool OWNER TO pwc_staging_owner;
        ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO pwc_staging;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO pwc_staging;
        REVOKE ALL ON chat_sandbox_pool FROM paperswithcode_user;
        REVOKE ALL ON chat_turn_latency FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_sandbox_pool OWNER TO paperswithcode_user;
        ALTER TABLE chat_turn_latency OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO paperswithcode_user;
        REVOKE ALL ON chat_sandbox_pool FROM pwc_staging;
        REVOKE ALL ON chat_turn_latency FROM pwc_staging;
    END IF;
END $$;

COMMIT;
