-- Migration: Remove redundant TASK_DATASETS table
--
-- Context: Task-dataset relationships are now defined via TASK_DATASET_METRICS.
-- A (task, dataset) pair is valid if it has at least one metric defined.
-- This aligns with the legacy PapersWithCode design where leaderboards are
-- defined by (task, dataset, metrics) triples.
--
-- Prerequisites:
-- 1. Run migrate_task_datasets_to_metrics.py to populate TASK_DATASET_METRICS
-- 2. Update all code to use TASK_DATASET_METRICS instead of TASK_DATASETS
-- 3. Test all API endpoints
--
-- This migration is idempotent and can be run multiple times.

-- Drop the redundant junction table
DROP TABLE IF EXISTS task_datasets CASCADE;

-- Verify the migration
DO $$
BEGIN
    -- Check that TASK_DATASET_METRICS has entries
    IF (SELECT COUNT(*) FROM task_dataset_metrics) = 0 THEN
        RAISE WARNING 'Warning: TASK_DATASET_METRICS is empty! This may indicate the data migration was not run.';
    ELSE
        RAISE NOTICE 'Success: TASK_DATASETS table dropped. Task-dataset relationships now managed via TASK_DATASET_METRICS.';
    END IF;
END $$;
