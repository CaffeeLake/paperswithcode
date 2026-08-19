-- Add a dedicated per-turn paper-selection snapshot for Highlight and Ask.
-- Apply with search_path=staging,public before activating ORM code that maps
-- chat_messages.paper_selection. Production remains separately unauthorized.

BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_paper_selection.sql must run with search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        RAISE EXCEPTION 'pwc_staging role must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS paper_selection JSONB;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        GRANT SELECT, UPDATE (paper_selection) ON chat_messages TO pwc_staging;
    ELSE
        GRANT SELECT, UPDATE (paper_selection) ON chat_messages TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
