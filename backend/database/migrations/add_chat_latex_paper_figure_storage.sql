-- Content-addressed private figure storage for immutable LaTeX-paper versions.
-- Apply after expand_chat_artifact_foundation.sql with the normal chat search_path.
BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_latex_paper_figure_storage.sql must run with search_path staging,public or public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_latex_paper_figure_blobs (
    digest VARCHAR(64) PRIMARY KEY,
    byte_count BIGINT NOT NULL,
    media_type VARCHAR(32) NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    CONSTRAINT chat_latex_paper_figure_blobs_digest_check CHECK (length(digest) = 64),
    CONSTRAINT chat_latex_paper_figure_blobs_bytes_check CHECK (byte_count > 0),
    CONSTRAINT chat_latex_paper_figure_blobs_type_check
        CHECK (media_type IN ('image/png','image/jpeg','application/pdf'))
);

CREATE TABLE IF NOT EXISTS chat_latex_paper_figure_references (
    version_id UUID NOT NULL REFERENCES chat_latex_paper_versions(id) ON DELETE CASCADE,
    path VARCHAR(300) NOT NULL,
    blob_digest VARCHAR(64) NOT NULL
        REFERENCES chat_latex_paper_figure_blobs(digest) ON DELETE RESTRICT,
    PRIMARY KEY (version_id, path),
    CONSTRAINT chat_latex_paper_figure_refs_digest_check CHECK (length(blob_digest) = 64)
);
CREATE INDEX IF NOT EXISTS idx_chat_latex_paper_figure_refs_digest
    ON chat_latex_paper_figure_references (blob_digest);

CREATE TABLE IF NOT EXISTS chat_latex_paper_storage_cleanup (
    storage_prefix TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_latex_paper_figure_blobs OWNER TO pwc_staging_owner;
        ALTER TABLE chat_latex_paper_figure_references OWNER TO pwc_staging_owner;
        ALTER TABLE chat_latex_paper_storage_cleanup OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_latex_paper_figure_blobs,
            chat_latex_paper_figure_references, chat_latex_paper_storage_cleanup TO pwc_staging;
        REVOKE ALL ON chat_latex_paper_figure_blobs,
            chat_latex_paper_figure_references, chat_latex_paper_storage_cleanup
            FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_latex_paper_figure_blobs OWNER TO paperswithcode_user;
        ALTER TABLE chat_latex_paper_figure_references OWNER TO paperswithcode_user;
        ALTER TABLE chat_latex_paper_storage_cleanup OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_latex_paper_figure_blobs,
            chat_latex_paper_figure_references, chat_latex_paper_storage_cleanup TO paperswithcode_user;
        REVOKE ALL ON chat_latex_paper_figure_blobs,
            chat_latex_paper_figure_references, chat_latex_paper_storage_cleanup
            FROM pwc_staging;
    END IF;
END $$;

COMMIT;
