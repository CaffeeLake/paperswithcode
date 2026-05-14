-- Migration: Add optional `harness` column to evaluations
--
-- Some benchmarks (e.g. Terminal-Bench) are effectively model+harness
-- combinations: the same model can score very differently when run inside
-- different agentic harnesses ("Claude Code", "Terminus", ...). This adds
-- an optional `harness` column so the leaderboard can display the harness
-- alongside the model instead of cramming both into `model_name`.
--
-- The migration also backfills the existing Terminal-Bench rows where the
-- harness was previously embedded in the model name in parentheses.
--
-- Created: 2026-05-12
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_evaluations_harness.sql

BEGIN;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS harness VARCHAR(255);

-- Backfill Terminal-Bench rows. All updates are scoped to the
-- `terminal-bench` dataset slug and match against the current model_name
-- so the migration is safe to re-run after the model names have been
-- normalized.
UPDATE evaluations e
SET
    model_name = 'GLM-5.1',
    harness = 'Claude Code'
FROM datasets d
WHERE e.dataset_id = d.id
  AND d.slug = 'terminal-bench'
  AND e.model_name = 'GLM-5.1 (best self-reported, Claude Code)';

UPDATE evaluations e
SET
    model_name = 'GLM-5.1',
    harness = 'Terminus-2'
FROM datasets d
WHERE e.dataset_id = d.id
  AND d.slug = 'terminal-bench'
  AND e.model_name = 'GLM-5.1 (Terminus-2)';

UPDATE evaluations e
SET
    model_name = 'GLM-4.5',
    harness = 'Terminus'
FROM datasets d
WHERE e.dataset_id = d.id
  AND d.slug = 'terminal-bench'
  AND e.model_name IN ('GLM-4.5 (355B)', 'GLM-4.5');

UPDATE evaluations e
SET harness = 'unknown'
FROM datasets d
WHERE e.dataset_id = d.id
  AND d.slug = 'terminal-bench'
  AND e.harness IS NULL
  AND e.model_name IN ('DeepSeek-V4-Pro Max', 'DeepSeek-V4-Flash Max');

COMMIT;
