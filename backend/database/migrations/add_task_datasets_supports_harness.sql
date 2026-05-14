-- Migration: Add harness support metadata to task_datasets
--
-- Harness support belongs to the task-dataset leaderboard, not the dataset
-- globally. Most leaderboards should keep harness values in methodology;
-- Terminal Bench 2.0 and SWE-Bench Verified currently expose model+harness
-- leaderboard semantics.
--
-- Created: 2026-05-12
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_task_datasets_supports_harness.sql

BEGIN;

ALTER TABLE task_datasets
    ADD COLUMN IF NOT EXISTS supports_harness BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE task_datasets td
SET supports_harness = TRUE,
    updated_at = NOW()
FROM datasets d
WHERE d.id = td.dataset_id
  AND d.name IN ('Terminal Bench 2.0', 'SWE-Bench Verified');

UPDATE evaluations e
SET harness = NULL,
    updated_at = NOW()
WHERE harness IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM task_datasets td
      WHERE td.task_id = e.task_id
        AND td.dataset_id = e.dataset_id
        AND td.supports_harness
  );

COMMENT ON COLUMN task_datasets.supports_harness IS
'Whether this task-dataset leaderboard allows values in evaluations.harness.';

COMMIT;
