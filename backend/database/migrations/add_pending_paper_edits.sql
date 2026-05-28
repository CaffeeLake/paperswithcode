-- Migration: Add pending_paper_edits table
--
-- Stores edit submissions from non-admin Hugging Face users for the paper-page
-- edit surfaces (tasks, methods, evaluation results, GitHub repositories,
-- project pages). Admin direct edits bypass this table and continue to mutate
-- live data through the existing admin endpoints.
--
-- Each row captures:
--   - which paper the edit targets (paper_id),
--   - who submitted it (hf_username),
--   - whether the submitter is a linked author of that paper at submit time
--     (is_author) -- used today to surface author-originated edits in review,
--     and tomorrow as a hook for auto-approving author edits,
--   - which edit surface it targets (edit_type),
--   - the proposed payload as JSONB whose shape matches what the existing
--     admin mutation endpoints expect (proposed_payload),
--   - an optional snapshot of the current live data at submit time so the
--     admin reviewer can diff against it (current_payload),
--   - moderation status + admin metadata.
--
-- Date: 2026-05-26

CREATE TABLE IF NOT EXISTS pending_paper_edits (
    id              BIGSERIAL PRIMARY KEY,
    paper_id        BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    hf_username     VARCHAR(255) NOT NULL,
    is_author       BOOLEAN NOT NULL DEFAULT FALSE,
    edit_type       VARCHAR(32) NOT NULL,
    proposed_payload JSONB NOT NULL,
    current_payload  JSONB,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    admin_note      TEXT,
    reviewed_by     VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    CONSTRAINT pending_paper_edits_edit_type_check CHECK (
        edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages', 'source_url')
    ),
    CONSTRAINT pending_paper_edits_status_check CHECK (
        status IN ('pending', 'approved', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_status_created_at
    ON pending_paper_edits(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_paper_edit_type
    ON pending_paper_edits(paper_id, edit_type);

CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_hf_username
    ON pending_paper_edits(hf_username);

-- Partial index over rows that are still pending: makes the future
-- "auto-approve when is_author" check cheap to scan.
CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_author_pending
    ON pending_paper_edits(is_author)
    WHERE status = 'pending';

COMMENT ON TABLE pending_paper_edits IS
'Edit submissions from non-admin Hugging Face users for paper-page surfaces. Approved rows are applied via the same backend mutation services that admin direct edits use; rejected/pending rows never affect live data. is_author flags submissions where the HF username matches a linked author of the paper.';
