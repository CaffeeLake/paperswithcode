-- Migration: Enable harness column for SWE-Bench Multilingual
--
-- SWE-Bench Multilingual uses the same model+harness leaderboard semantics as
-- SWE-Bench Verified so agent scaffolds like Mini-SWE-Agent can live in
-- evaluations.harness instead of model_name suffixes.
--
-- Created: 2026-06-16
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/enable_swe_bench_multilingual_harness.sql

BEGIN;

UPDATE task_datasets td
SET supports_harness = TRUE,
    updated_at = NOW()
FROM tasks t,
     datasets d
WHERE td.task_id = t.id
  AND td.dataset_id = d.id
  AND t.slug = 'coding-agents'
  AND d.slug = 'swe-bench-multilingual';

COMMENT ON COLUMN task_datasets.supports_harness IS
'Whether this task-dataset leaderboard allows values in evaluations.harness.';

COMMIT;
