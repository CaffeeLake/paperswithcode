BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_turn_latency.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (
           SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner'
       ) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_turn_latency (
    turn_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    chat_session_id UUID NOT NULL
        REFERENCES chat_sessions(id) ON DELETE CASCADE,
    traffic_class VARCHAR(24) NOT NULL
        CHECK (traffic_class IN ('new_chat','followup')),
    execution_backend VARCHAR(24) NOT NULL
        CHECK (execution_backend IN ('local_mcp','modal_cli')),
    acquisition_outcome VARCHAR(24) NOT NULL DEFAULT 'pending'
        CHECK (
            acquisition_outcome IN
            ('pending','created','reused_session','pool_hit','pool_miss')
        ),
    model_route VARCHAR(255) NOT NULL,
    app_release_id VARCHAR(255) NOT NULL,
    sandbox_image_version VARCHAR(255),
    worker_contract_version VARCHAR(64),
    pwc_cli_version VARCHAR(64),
    system_prompt_sha256 VARCHAR(64),
    acquisition_started_ms INTEGER,
    pool_lookup_completed_ms INTEGER,
    modal_sandbox_created_ms INTEGER,
    worker_control_ready_ms INTEGER,
    session_assignment_completed_ms INTEGER,
    broker_capability_installed_ms INTEGER,
    sdk_query_dispatched_ms INTEGER,
    provider_gateway_received_ms INTEGER,
    upstream_response_headers_ms INTEGER,
    upstream_first_body_byte_ms INTEGER,
    first_worker_delta_ms INTEGER,
    first_application_sse_delta_ms INTEGER,
    total_ms INTEGER,
    browser_stream_start_ms INTEGER,
    browser_first_visible_delta_ms INTEGER,
    browser_terminal_classification VARCHAR(24)
        CHECK (
            browser_terminal_classification IS NULL
            OR browser_terminal_classification IN
                ('complete','stopped','error','network_error','aborted')
        ),
    terminal_status VARCHAR(24) NOT NULL DEFAULT 'running'
        CHECK (
            terminal_status IN
            ('running','complete','stopped','error','interrupted')
        ),
    admitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_turn_latency_admitted
    ON chat_turn_latency (admitted_at, turn_id);
CREATE INDEX IF NOT EXISTS idx_chat_turn_latency_session
    ON chat_turn_latency (chat_session_id);

ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO pwc_staging;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        REVOKE ALL ON chat_turn_latency FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
