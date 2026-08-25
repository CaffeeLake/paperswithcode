BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'allow_chat_latex_paper_restore_digests.sql must run with search_path staging,public or public';
    END IF;
END $$;

-- A restore creates a new immutable version from an older source snapshot, so
-- the same content digest can legitimately occur more than once per artifact.
-- Version numbering remains unique and is the durable history identity.
ALTER TABLE chat_latex_paper_versions
    DROP CONSTRAINT IF EXISTS uq_chat_latex_paper_versions_digest;

COMMIT;
