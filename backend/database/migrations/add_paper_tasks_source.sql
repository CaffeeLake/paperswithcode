-- Migration: Add `source` column to paper_tasks
-- Description: Tracks whether a paper<->task link was created by automatic
--              keyword matching ('auto') or by a manual admin action ('manual').
--              Lets the keyword-matching rebuild pass safely delete & re-create
--              'auto' rows without clobbering hand-curated tags.
-- Date: 2026-05-11

ALTER TABLE paper_tasks
ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'auto';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'paper_tasks_source_check'
    ) THEN
        ALTER TABLE paper_tasks
        ADD CONSTRAINT paper_tasks_source_check
        CHECK (source IN ('auto', 'manual'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_paper_tasks_source
ON paper_tasks(source);

COMMENT ON COLUMN paper_tasks.source IS
'How this link was created: ''auto'' = inserted by keyword matcher, ''manual'' = set via admin API or one-off script. Rebuild pass only deletes/re-inserts auto rows.';
