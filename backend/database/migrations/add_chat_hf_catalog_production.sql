BEGIN;

-- Production counterpart to add_chat_hf_catalog.sql. The counters remain
-- required by the common capability model even when admission is closed.
SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_hf_catalog_production.sql must run in public';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        RAISE EXCEPTION
            'paperswithcode_user must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS hf_catalog_calls INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS hf_recursive_list_calls INTEGER NOT NULL DEFAULT 0;

GRANT SELECT, UPDATE (hf_catalog_calls, hf_recursive_list_calls)
    ON chat_turn_capabilities TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        REVOKE UPDATE (hf_catalog_calls, hf_recursive_list_calls)
            ON chat_turn_capabilities FROM pwc_staging;
    END IF;
END $$;

COMMIT;
