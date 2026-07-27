-- Remove manual benchmark pinning. Task pages now rank benchmarks using the
-- benchmark trending signal instead of task_datasets.featured_rank.

DROP INDEX IF EXISTS idx_task_datasets_featured_rank;

ALTER TABLE task_datasets
DROP CONSTRAINT IF EXISTS task_datasets_featured_rank_positive;

ALTER TABLE task_datasets
DROP COLUMN IF EXISTS featured_rank;
