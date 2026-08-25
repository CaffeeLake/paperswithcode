-- Safe rollback for expand_chat_artifact_foundation.sql. This deliberately
-- refuses to discard paper state; remove or migrate those records first.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM chat_latex_paper_versions)
       OR EXISTS (SELECT 1 FROM chat_artifacts WHERE kind = 'latex_paper') THEN
        RAISE EXCEPTION 'cannot roll back artifact foundation while latex_paper rows exist';
    END IF;
END $$;

DROP INDEX IF EXISTS idx_chat_artifacts_preview_head;
DROP INDEX IF EXISTS idx_chat_artifacts_source_head;
DROP INDEX IF EXISTS uq_chat_artifacts_session_latex_paper;

ALTER TABLE chat_artifacts
    DROP CONSTRAINT IF EXISTS chat_artifacts_preview_head_version_fkey,
    DROP CONSTRAINT IF EXISTS chat_artifacts_source_head_version_fkey;
ALTER TABLE chat_artifacts
    DROP COLUMN IF EXISTS preview_head_version_id,
    DROP COLUMN IF EXISTS source_head_version_id;
DROP TABLE IF EXISTS chat_latex_paper_versions;

ALTER TABLE chat_artifacts
    DROP CONSTRAINT IF EXISTS chat_artifacts_kind_check;
ALTER TABLE chat_artifacts
    ADD CONSTRAINT chat_artifacts_kind_check CHECK (kind = 'posterly');

COMMIT;
