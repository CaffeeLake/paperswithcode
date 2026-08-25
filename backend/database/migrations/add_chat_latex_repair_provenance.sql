-- Preserve selected-model provenance for durable successful LaTeX repairs.
-- Apply after expand_chat_artifact_foundation.sql.
BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION 'add_chat_latex_repair_provenance.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_latex_paper_versions
    ADD COLUMN IF NOT EXISTS generation_provenance JSONB;

COMMIT;
