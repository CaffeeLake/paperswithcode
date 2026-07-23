BEGIN;

CREATE TABLE IF NOT EXISTS paper_curation_jobs (
    id UUID PRIMARY KEY,
    kind VARCHAR(32) NOT NULL CHECK (kind IN ('add-evals', 'enrich-paper')),
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    paper_route VARCHAR(255) NOT NULL,
    paper_title TEXT NOT NULL,
    requested_by VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'dispatching', 'running', 'completed', 'failed', 'canceled')),
    hf_job_id VARCHAR(64) UNIQUE,
    callback_token_hash VARCHAR(64),
    report TEXT,
    error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_queue
    ON paper_curation_jobs (status, created_at);
CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_paper
    ON paper_curation_jobs (paper_id, created_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON paper_curation_jobs TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
