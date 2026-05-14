-- Migration: Add `methods_scanned_at` column to `papers`.
-- Description: Tracks the last time a paper's references were checked against
--              `methods.source_paper_id` so we can run an incremental weekly
--              cron (`link_methods_by_references`) without rescanning every
--              paper. NULL means the paper has not been scanned yet.
--
--              Existing papers were already covered by the bulk citation-based
--              pass (`link_papers_by_source_citations.py --write`), so we mark
--              them as scanned to keep the cron focused on freshly imported
--              papers going forward.
-- Date: 2026-05-12

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS methods_scanned_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_papers_methods_scanned_at
ON papers(methods_scanned_at)
WHERE methods_scanned_at IS NULL;

COMMENT ON COLUMN papers.methods_scanned_at IS
'When the references-based method tagging cron last processed this paper. '
'NULL means it has never been scanned and is eligible for the next run.';

-- Backfill: existing papers were already covered by the citation-based
-- bulk pass. Mark them as scanned so the weekly cron only picks up
-- papers added after this migration.
UPDATE papers
SET methods_scanned_at = NOW()
WHERE methods_scanned_at IS NULL;
