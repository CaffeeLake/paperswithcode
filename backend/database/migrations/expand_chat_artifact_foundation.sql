-- Additive foundation for private LaTeX-paper artifacts. Apply after
-- add_chat_artifacts.sql, with the environment's normal chat search_path.
-- Existing Posterly rows retain NULL paper-head fields and unchanged routes.
BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'expand_chat_artifact_foundation.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_artifacts
    DROP CONSTRAINT IF EXISTS chat_artifacts_kind_check;
ALTER TABLE chat_artifacts
    ADD CONSTRAINT chat_artifacts_kind_check
    CHECK (kind IN ('posterly', 'latex_paper'));

ALTER TABLE chat_artifacts
    ADD COLUMN IF NOT EXISTS source_head_version_id UUID,
    ADD COLUMN IF NOT EXISTS preview_head_version_id UUID;

CREATE TABLE IF NOT EXISTS chat_latex_paper_versions (
    id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES chat_artifacts(id) ON DELETE CASCADE,
    parent_version_id UUID REFERENCES chat_latex_paper_versions(id) ON DELETE SET NULL,
    turn_id UUID,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    version INTEGER NOT NULL,
    source_manifest JSONB NOT NULL,
    source_digest VARCHAR(64) NOT NULL,
    source_byte_count BIGINT NOT NULL,
    storage_key TEXT NOT NULL,
    compiled_pdf_path VARCHAR(300),
    storage_state VARCHAR(16) NOT NULL,
    compile_status VARCHAR(16) NOT NULL,
    compile_diagnostics JSONB,
    display_metadata JSONB NOT NULL,
    generation_provenance JSONB,
    actor_type VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_latex_paper_versions_number_check CHECK (version >= 1),
    CONSTRAINT chat_latex_paper_versions_bytes_check CHECK (source_byte_count >= 0),
    CONSTRAINT chat_latex_paper_versions_source_digest_check
        CHECK (length(source_digest) = 64),
    CONSTRAINT chat_latex_paper_versions_storage_state_check
        CHECK (storage_state IN ('uploading','ready','failed','deleting')),
    CONSTRAINT chat_latex_paper_versions_compile_status_check
        CHECK (compile_status IN ('queued','compiling','succeeded','failed')),
    CONSTRAINT chat_latex_paper_versions_preview_check
        CHECK (
            (compile_status = 'succeeded' AND compiled_pdf_path IS NOT NULL)
            OR (compile_status <> 'succeeded' AND compiled_pdf_path IS NULL)
        ),
    CONSTRAINT chat_latex_paper_versions_actor_type_check
        CHECK (actor_type IN ('ai','human','restore')),
    CONSTRAINT uq_chat_latex_paper_versions_number UNIQUE (artifact_id, version),
    CONSTRAINT uq_chat_latex_paper_versions_digest UNIQUE (artifact_id, source_digest)
);

CREATE INDEX IF NOT EXISTS idx_chat_latex_paper_versions_turn
    ON chat_latex_paper_versions (turn_id);
CREATE INDEX IF NOT EXISTS idx_chat_latex_paper_versions_message
    ON chat_latex_paper_versions (message_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chat_artifacts_source_head_version_fkey'
    ) THEN
        ALTER TABLE chat_artifacts
            ADD CONSTRAINT chat_artifacts_source_head_version_fkey
            FOREIGN KEY (source_head_version_id) REFERENCES chat_latex_paper_versions(id)
            ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chat_artifacts_preview_head_version_fkey'
    ) THEN
        ALTER TABLE chat_artifacts
            ADD CONSTRAINT chat_artifacts_preview_head_version_fkey
            FOREIGN KEY (preview_head_version_id) REFERENCES chat_latex_paper_versions(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- PostgreSQL enforces the one-paper-per-session invariant without changing
-- Posterly's existing identifier uniqueness or artifact-count behavior.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_artifacts_session_latex_paper
    ON chat_artifacts (session_id)
    WHERE kind = 'latex_paper';
CREATE INDEX IF NOT EXISTS idx_chat_artifacts_source_head
    ON chat_artifacts (source_head_version_id)
    WHERE source_head_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_artifacts_preview_head
    ON chat_artifacts (preview_head_version_id)
    WHERE preview_head_version_id IS NOT NULL;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_latex_paper_versions OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_latex_paper_versions
            TO pwc_staging;
        REVOKE ALL ON chat_latex_paper_versions FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_latex_paper_versions OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_latex_paper_versions
            TO paperswithcode_user;
        REVOKE ALL ON chat_latex_paper_versions FROM pwc_staging;
    END IF;
END $$;

COMMIT;
