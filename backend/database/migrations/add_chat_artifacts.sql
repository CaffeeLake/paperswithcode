-- Staging-only durable Posterly artifacts and public share snapshots.
-- Run with search_path=staging,public before activating the ORM release.

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_artifacts.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS artifact_paper_id VARCHAR(64);

CREATE TABLE IF NOT EXISTS chat_artifacts (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    identifier VARCHAR(80) NOT NULL,
    kind VARCHAR(24) NOT NULL,
    title VARCHAR(300) NOT NULL,
    latest_version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_artifacts_kind_check CHECK (kind = 'posterly'),
    CONSTRAINT chat_artifacts_version_check CHECK (latest_version >= 0),
    CONSTRAINT uq_chat_artifacts_session_identifier UNIQUE (session_id, identifier)
);

CREATE INDEX IF NOT EXISTS idx_chat_artifacts_session
    ON chat_artifacts (session_id, created_at);

CREATE TABLE IF NOT EXISTS chat_artifact_versions (
    id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES chat_artifacts(id) ON DELETE CASCADE,
    turn_id UUID NOT NULL,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    version INTEGER NOT NULL,
    manifest JSONB NOT NULL,
    bundle_digest VARCHAR(64) NOT NULL,
    byte_count BIGINT NOT NULL,
    storage_key TEXT NOT NULL,
    preview_path VARCHAR(300) NOT NULL,
    preview_mime VARCHAR(64) NOT NULL,
    gate_status VARCHAR(16) NOT NULL,
    state VARCHAR(16) NOT NULL,
    failure_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_artifact_versions_number_check CHECK (version >= 1),
    CONSTRAINT chat_artifact_versions_bytes_check CHECK (byte_count >= 0),
    CONSTRAINT chat_artifact_versions_gate_check
        CHECK (gate_status IN ('passed','warnings','failed')),
    CONSTRAINT chat_artifact_versions_state_check
        CHECK (state IN ('uploading','ready','failed','deleting')),
    CONSTRAINT uq_chat_artifact_versions_number UNIQUE (artifact_id, version),
    CONSTRAINT uq_chat_artifact_versions_digest UNIQUE (artifact_id, bundle_digest)
);

CREATE INDEX IF NOT EXISTS idx_chat_artifact_versions_turn
    ON chat_artifact_versions (turn_id);
CREATE INDEX IF NOT EXISTS idx_chat_artifact_versions_message
    ON chat_artifact_versions (message_id);

CREATE TABLE IF NOT EXISTS chat_shared_artifacts (
    id UUID PRIMARY KEY,
    share_id UUID NOT NULL REFERENCES chat_shares(id) ON DELETE CASCADE,
    capability_id UUID NOT NULL UNIQUE,
    source_version_id UUID NOT NULL,
    identifier VARCHAR(80) NOT NULL,
    title VARCHAR(300) NOT NULL,
    canvas JSONB NOT NULL,
    gate_status VARCHAR(16) NOT NULL,
    digest VARCHAR(64) NOT NULL,
    storage_key TEXT NOT NULL,
    preview_path VARCHAR(300) NOT NULL,
    pdf_path VARCHAR(300),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_shared_artifacts_gate_check
        CHECK (gate_status IN ('passed','warnings','failed')),
    CONSTRAINT chat_shared_artifacts_failed_pdf_check
        CHECK (gate_status <> 'failed' OR pdf_path IS NULL),
    CONSTRAINT uq_chat_shared_artifacts_identifier UNIQUE (share_id, identifier)
);

CREATE INDEX IF NOT EXISTS idx_chat_shared_artifacts_share
    ON chat_shared_artifacts (share_id);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_artifacts OWNER TO pwc_staging_owner;
        ALTER TABLE chat_artifact_versions OWNER TO pwc_staging_owner;
        ALTER TABLE chat_shared_artifacts OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            chat_artifacts, chat_artifact_versions, chat_shared_artifacts
            TO pwc_staging;
        REVOKE ALL ON
            chat_artifacts, chat_artifact_versions, chat_shared_artifacts
            FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_artifacts OWNER TO paperswithcode_user;
        ALTER TABLE chat_artifact_versions OWNER TO paperswithcode_user;
        ALTER TABLE chat_shared_artifacts OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            chat_artifacts, chat_artifact_versions, chat_shared_artifacts
            TO paperswithcode_user;
        REVOKE ALL ON
            chat_artifacts, chat_artifact_versions, chat_shared_artifacts
            FROM pwc_staging;
    END IF;
END $$;
