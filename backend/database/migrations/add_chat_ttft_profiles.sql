BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_ttft_profiles.sql requires search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_sandbox_pool
    ADD COLUMN IF NOT EXISTS agent_harness VARCHAR(16) NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS agent_harness_version VARCHAR(64) NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS model_profile VARCHAR(255) NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS reasoning_profile VARCHAR(16) NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS prompt_digest VARCHAR(64) NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS provider_adapter_contract VARCHAR(64) NOT NULL DEFAULT 'generic';

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS control_connection_ms INTEGER,
    ADD COLUMN IF NOT EXISTS agent_spawn_ms INTEGER,
    ADD COLUMN IF NOT EXISTS agent_startup_ready_ms INTEGER,
    ADD COLUMN IF NOT EXISTS session_bind_restore_ms INTEGER,
    ADD COLUMN IF NOT EXISTS resource_loading_ms INTEGER,
    ADD COLUMN IF NOT EXISTS agent_session_ready_ms INTEGER,
    ADD COLUMN IF NOT EXISTS first_semantic_event_ms INTEGER,
    ADD COLUMN IF NOT EXISTS browser_first_reasoning_delta_ms INTEGER,
    ADD COLUMN IF NOT EXISTS browser_first_tool_call_ms INTEGER,
    ADD COLUMN IF NOT EXISTS browser_first_answer_delta_ms INTEGER,
    ADD COLUMN IF NOT EXISTS pool_miss_reason VARCHAR(32),
    ADD COLUMN IF NOT EXISTS session_reuse_cohort VARCHAR(32);

ALTER TABLE chat_openrouter_provider_calls
    ADD COLUMN IF NOT EXISTS upstream_provider VARCHAR(128),
    ADD COLUMN IF NOT EXISTS routing_policy VARCHAR(24) NOT NULL DEFAULT 'throughput',
    ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS cache_creation_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS provider_ttft_ms INTEGER,
    ADD COLUMN IF NOT EXISTS fallback_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chat_openrouter_provider_calls
    ADD COLUMN IF NOT EXISTS request_bytes INTEGER,
    ADD COLUMN IF NOT EXISTS system_token_bucket INTEGER,
    ADD COLUMN IF NOT EXISTS tool_token_bucket INTEGER,
    ADD COLUMN IF NOT EXISTS conversation_token_bucket INTEGER;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_sandbox_pool OWNER TO pwc_staging_owner;
        ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
        ALTER TABLE chat_openrouter_provider_calls OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO pwc_staging;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO pwc_staging;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_openrouter_provider_calls TO pwc_staging;
        REVOKE ALL ON chat_sandbox_pool FROM paperswithcode_user;
        REVOKE ALL ON chat_turn_latency FROM paperswithcode_user;
        REVOKE ALL ON chat_openrouter_provider_calls FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_sandbox_pool OWNER TO paperswithcode_user;
        ALTER TABLE chat_turn_latency OWNER TO paperswithcode_user;
        ALTER TABLE chat_openrouter_provider_calls OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_openrouter_provider_calls TO paperswithcode_user;
        REVOKE ALL ON chat_sandbox_pool FROM pwc_staging;
        REVOKE ALL ON chat_turn_latency FROM pwc_staging;
        REVOKE ALL ON chat_openrouter_provider_calls FROM pwc_staging;
    END IF;
END $$;

COMMIT;
