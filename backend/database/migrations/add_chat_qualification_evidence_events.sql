BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_qualification_evidence_events.sql requires staging or public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_qualification_evidence_events (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE,
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    operation_digest VARCHAR(64),
    occurred_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chat_qualification_evidence_event_type_check
        CHECK (event_type IN (
            'executor_started',
            'stale_fence',
            'queued',
            'workspace_created',
            'workspace_reused',
            'workspace_evicted'
        )),
    CONSTRAINT chat_qualification_evidence_operation_shape_check
        CHECK (
            (event_type = 'executor_started') = (operation_digest IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_chat_qualification_evidence_session_time
    ON chat_qualification_evidence_events (chat_session_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_chat_qualification_evidence_turn_event
    ON chat_qualification_evidence_events (turn_id, event_type);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_qualification_evidence_events OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON chat_qualification_evidence_events TO pwc_staging;
        REVOKE ALL ON chat_qualification_evidence_events FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_qualification_evidence_events OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON chat_qualification_evidence_events TO paperswithcode_user;
        REVOKE ALL ON chat_qualification_evidence_events FROM pwc_staging;
    END IF;
END $$;

COMMIT;
