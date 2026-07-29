-- Additive, append-only audit and idempotency storage for paper-page curation.
CREATE TABLE IF NOT EXISTS catalog_mutation_events (
    id UUID PRIMARY KEY,
    actor_hf_subject VARCHAR(255) NOT NULL,
    actor_username VARCHAR(255),
    actor_role VARCHAR(32) NOT NULL
        CHECK (actor_role IN ('admin', 'contributor')),
    operation VARCHAR(32) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    before_snapshot JSONB,
    after_snapshot JSONB,
    request_id VARCHAR(255) NOT NULL,
    source_environment VARCHAR(32) NOT NULL,
    release_id VARCHAR(255) NOT NULL,
    rollback_of_event_id UUID REFERENCES catalog_mutation_events(id) ON DELETE RESTRICT,
    schema_version SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_catalog_mutation_events_actor
    ON catalog_mutation_events(actor_hf_subject, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_catalog_mutation_events_created
    ON catalog_mutation_events(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS catalog_mutation_idempotency (
    actor_hf_subject VARCHAR(255) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    result_snapshot JSONB NOT NULL,
    event_id UUID NOT NULL REFERENCES catalog_mutation_events(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_hf_subject, idempotency_key)
);

CREATE TABLE IF NOT EXISTS catalog_audit_read_progress (
    admin_hf_subject VARCHAR(255) PRIMARY KEY,
    read_through_created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE catalog_mutation_events IS
'Append-only paper-page catalog mutation ledger; application code exposes no delete operation.';

CREATE OR REPLACE FUNCTION reject_catalog_mutation_event_rewrite()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'catalog_mutation_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS catalog_mutation_events_append_only
    ON catalog_mutation_events;
CREATE TRIGGER catalog_mutation_events_append_only
BEFORE UPDATE OR DELETE ON catalog_mutation_events
FOR EACH ROW EXECUTE FUNCTION reject_catalog_mutation_event_rewrite();

DROP TRIGGER IF EXISTS catalog_mutation_events_no_truncate
    ON catalog_mutation_events;
CREATE TRIGGER catalog_mutation_events_no_truncate
BEFORE TRUNCATE ON catalog_mutation_events
FOR EACH STATEMENT EXECUTE FUNCTION reject_catalog_mutation_event_rewrite();
