BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_qualification_metadata.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS qualification_run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS qualification_scenario VARCHAR(32);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chat_turn_latency_qualification_scenario_check'
          AND conrelid = 'chat_turn_latency'::regclass
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_qualification_scenario_check
            CHECK (
                qualification_scenario IS NULL
                OR qualification_scenario IN (
                    'focused_latency',
                    'reliability',
                    'clean_cancel',
                    'forced_failure'
                )
            );
    END IF;
END $$;

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
