BEGIN;

-- Pi chat state is staging-only until production chat receives separate
-- authorization. Force the environment-owned schema even for superusers.
SET LOCAL search_path = staging, public;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_pi_harness.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
        RAISE EXCEPTION 'staging database roles are required';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS agent_harness VARCHAR(16) NOT NULL DEFAULT 'claude';
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS agent_harness VARCHAR(16),
    ADD COLUMN IF NOT EXISTS agent_resume_boundary_id TEXT;
ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS agent_harness VARCHAR(16) NOT NULL DEFAULT 'claude',
    ADD COLUMN IF NOT EXISTS pi_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS first_semantic_event_class VARCHAR(16);
ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS agent_harness VARCHAR(16) NOT NULL DEFAULT 'claude';

UPDATE chat_messages SET agent_harness = 'claude' WHERE agent_harness IS NULL;
UPDATE chat_messages
SET agent_resume_boundary_id = sdk_resume_boundary_id::text
WHERE agent_resume_boundary_id IS NULL AND sdk_resume_boundary_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_sessions'::regclass AND conname = 'chat_sessions_agent_harness_check') THEN
        ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_agent_harness_check CHECK (agent_harness IN ('claude','pi'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_messages'::regclass AND conname = 'chat_messages_agent_harness_check') THEN
        ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_agent_harness_check CHECK (agent_harness IS NULL OR agent_harness IN ('claude','pi'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_turn_latency'::regclass AND conname = 'chat_turn_latency_agent_harness_check') THEN
        ALTER TABLE chat_turn_latency ADD CONSTRAINT chat_turn_latency_agent_harness_check CHECK (agent_harness IN ('claude','pi'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_turn_latency'::regclass AND conname = 'chat_turn_latency_semantic_event_check') THEN
        ALTER TABLE chat_turn_latency ADD CONSTRAINT chat_turn_latency_semantic_event_check CHECK (first_semantic_event_class IS NULL OR first_semantic_event_class IN ('reasoning','tool','answer'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_turn_capabilities'::regclass AND conname = 'chat_turn_capabilities_agent_harness_check') THEN
        ALTER TABLE chat_turn_capabilities ADD CONSTRAINT chat_turn_capabilities_agent_harness_check CHECK (agent_harness IN ('claude','pi'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_pi_sessions (
    agent_session_id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL UNIQUE REFERENCES chat_sessions(id) ON DELETE CASCADE,
    current_leaf_id TEXT,
    entry_count BIGINT NOT NULL DEFAULT 0,
    byte_size BIGINT NOT NULL DEFAULT 0,
    format_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_pi_sessions_nonnegative_check CHECK (entry_count >= 0 AND byte_size >= 0),
    CONSTRAINT chat_pi_sessions_format_version_check CHECK (format_version = 1)
);

CREATE TABLE IF NOT EXISTS chat_pi_transcript_entries (
    id BIGSERIAL PRIMARY KEY,
    agent_session_id UUID NOT NULL REFERENCES chat_pi_sessions(agent_session_id) ON DELETE CASCADE,
    ordinal BIGINT NOT NULL,
    entry_id TEXT,
    parent_entry_id TEXT,
    entry_type VARCHAR(64) NOT NULL,
    entry JSONB NOT NULL,
    byte_size INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_pi_transcript_entries_bounds_check CHECK (ordinal >= 0 AND byte_size >= 2 AND byte_size <= 1048576),
    CONSTRAINT uq_chat_pi_transcript_entries_ordinal UNIQUE (agent_session_id, ordinal)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_pi_transcript_entries_entry_id
    ON chat_pi_transcript_entries (agent_session_id, entry_id)
    WHERE entry_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS chat_pi_prepared_forks (
    fork_session_id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    source_session_id UUID NOT NULL,
    boundary_entry_id TEXT NOT NULL,
    entries JSONB NOT NULL,
    entry_count BIGINT NOT NULL,
    byte_size BIGINT NOT NULL,
    format_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_pi_prepared_forks_bounds_check
        CHECK (entry_count >= 1 AND byte_size >= 2 AND format_version = 1)
);
CREATE INDEX IF NOT EXISTS idx_chat_pi_prepared_forks_chat
    ON chat_pi_prepared_forks (chat_session_id);

CREATE TABLE IF NOT EXISTS chat_harness_assignment_audit (
    id BIGSERIAL PRIMARY KEY,
    chat_session_id UUID NOT NULL UNIQUE REFERENCES chat_sessions(id) ON DELETE CASCADE,
    agent_harness VARCHAR(16) NOT NULL,
    assignment_source VARCHAR(24) NOT NULL,
    operator_subject_hash VARCHAR(64),
    app_release_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_harness_assignment_audit_harness_check CHECK (agent_harness IN ('claude','pi')),
    CONSTRAINT chat_harness_assignment_audit_source_check CHECK (assignment_source IN ('default','cutover','admin_override'))
);

ALTER TABLE chat_pi_sessions OWNER TO pwc_staging_owner;
ALTER TABLE chat_pi_transcript_entries OWNER TO pwc_staging_owner;
ALTER TABLE chat_pi_prepared_forks OWNER TO pwc_staging_owner;
ALTER SEQUENCE chat_pi_transcript_entries_id_seq OWNER TO pwc_staging_owner;
ALTER TABLE chat_harness_assignment_audit OWNER TO pwc_staging_owner;
ALTER SEQUENCE chat_harness_assignment_audit_id_seq OWNER TO pwc_staging_owner;

GRANT SELECT, INSERT, UPDATE, DELETE ON chat_pi_sessions TO pwc_staging;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_pi_transcript_entries TO pwc_staging;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_pi_prepared_forks TO pwc_staging;
GRANT USAGE, SELECT ON SEQUENCE chat_pi_transcript_entries_id_seq TO pwc_staging;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_harness_assignment_audit TO pwc_staging;
GRANT USAGE, SELECT ON SEQUENCE chat_harness_assignment_audit_id_seq TO pwc_staging;
GRANT SELECT, INSERT, UPDATE (agent_harness) ON chat_sessions TO pwc_staging;
GRANT SELECT, INSERT, UPDATE (agent_harness, agent_resume_boundary_id) ON chat_messages TO pwc_staging;
GRANT SELECT, INSERT, UPDATE (agent_harness, pi_version, first_semantic_event_class) ON chat_turn_latency TO pwc_staging;
GRANT SELECT, INSERT, UPDATE (agent_harness) ON chat_turn_capabilities TO pwc_staging;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        REVOKE ALL ON chat_pi_sessions, chat_pi_transcript_entries, chat_pi_prepared_forks, chat_harness_assignment_audit FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
