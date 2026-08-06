BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_active_cost.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS sandbox_cpu_request NUMERIC(8, 3),
    ADD COLUMN IF NOT EXISTS sandbox_memory_request_mib INTEGER,
    ADD COLUMN IF NOT EXISTS estimated_active_cost_usd NUMERIC(14, 8);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO pwc_staging;
        REVOKE ALL ON chat_turn_latency FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_turn_latency OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO paperswithcode_user;
        REVOKE ALL ON chat_turn_latency FROM pwc_staging;
    END IF;
END $$;

COMMIT;
