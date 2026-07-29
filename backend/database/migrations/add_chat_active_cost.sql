BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_active_cost.sql must run with search_path staging,public';
    END IF;
END $$;

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS sandbox_cpu_request NUMERIC(8, 3),
    ADD COLUMN IF NOT EXISTS sandbox_memory_request_mib INTEGER,
    ADD COLUMN IF NOT EXISTS estimated_active_cost_usd NUMERIC(14, 8);

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
