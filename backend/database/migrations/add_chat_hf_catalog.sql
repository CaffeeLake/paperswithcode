DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION 'add_chat_hf_catalog.sql must run with search_path staging,public';
    END IF;
END $$;

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS hf_catalog_calls integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS hf_recursive_list_calls integer NOT NULL DEFAULT 0;
