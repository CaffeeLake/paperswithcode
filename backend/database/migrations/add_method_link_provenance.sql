BEGIN;

CREATE TABLE IF NOT EXISTS paper_method_evidence (
    paper_id BIGINT NOT NULL,
    method_id BIGINT NOT NULL,
    evidence_type VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NULL,
    PRIMARY KEY (paper_id, method_id, evidence_type),
    CONSTRAINT paper_method_evidence_parent_fk
        FOREIGN KEY (paper_id, method_id)
        REFERENCES paper_methods(paper_id, method_id) ON DELETE CASCADE,
    CONSTRAINT paper_method_evidence_type_check CHECK (
        evidence_type IN ('source', 'keyword', 'reference', 'manual', 'legacy_unknown')
    )
);
CREATE INDEX IF NOT EXISTS idx_paper_method_evidence_method_type
    ON paper_method_evidence(method_id, evidence_type);

CREATE TABLE IF NOT EXISTS paper_method_exclusions (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    method_id BIGINT NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, method_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_method_exclusions_method
    ON paper_method_exclusions(method_id, paper_id);

CREATE TABLE IF NOT EXISTS method_reference_backfill_months (
    method_id BIGINT NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
    month_start DATE NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    eligible_papers INTEGER NOT NULL DEFAULT 0,
    processed_papers INTEGER NOT NULL DEFAULT 0,
    matched_papers INTEGER NOT NULL DEFAULT 0,
    unresolvable_papers INTEGER NOT NULL DEFAULT 0,
    retryable_failures INTEGER NOT NULL DEFAULT 0,
    cursor_published_at DATE NULL,
    cursor_paper_id BIGINT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT NULL,
    PRIMARY KEY (method_id, month_start),
    CONSTRAINT method_reference_backfill_months_status_check CHECK (
        status IN ('pending', 'running', 'complete', 'failed')
    )
);
CREATE INDEX IF NOT EXISTS idx_method_reference_backfill_status
    ON method_reference_backfill_months(status, updated_at);

CREATE TABLE IF NOT EXISTS method_keyword_backfill_runs (
    keyword_catalog_sha256 CHAR(64) PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    eligible_papers INTEGER NOT NULL DEFAULT 0,
    processed_papers INTEGER NOT NULL DEFAULT 0,
    cursor_paper_id BIGINT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT NULL,
    CONSTRAINT method_keyword_backfill_runs_status_check CHECK (
        status IN ('pending', 'running', 'complete', 'failed')
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_method_keyword_backfill_one_running
    ON method_keyword_backfill_runs(status) WHERE status = 'running';

-- Recover evidence that can be established deterministically without guessing.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE source_paper_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE source_paper_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT pm.paper_id, pm.method_id, 'legacy_unknown'
FROM paper_methods pm
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_evidence e
    WHERE e.paper_id = pm.paper_id AND e.method_id = pm.method_id
)
ON CONFLICT DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            paper_method_evidence,
            paper_method_exclusions,
            method_reference_backfill_months,
            method_keyword_backfill_runs
        TO paperswithcode_user;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON
            paper_method_evidence,
            paper_method_exclusions,
            method_reference_backfill_months,
            method_keyword_backfill_runs
        TO pwc_staging;
    END IF;
END
$$;

COMMIT;
