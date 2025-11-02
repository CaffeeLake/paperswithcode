-- Migration: Consolidate duplicate "score" and "Score" metrics
-- Consolidates to lowercase "score" (id: 43) as the canonical version
--
-- Created: November 2025
-- Usage: psql -U paperswithcode_user -h localhost -d paperswithcode_hf -f backend/database/migration/consolidate_score_metric.sql

BEGIN;

-- Step 1: Update evaluations using "Score" to use "score"
UPDATE evaluations
SET best_metric = 'score'
WHERE best_metric = 'Score';

-- Step 2: Update task_dataset_metrics to use the canonical metric_id (43)
-- First, add triples for metric_id 43 where only 44 exists
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT DISTINCT
    tdm.task_id,
    tdm.dataset_id,
    43 AS metric_id,  -- canonical "score" id
    CURRENT_TIMESTAMP
FROM task_dataset_metrics tdm
WHERE tdm.metric_id = 44  -- "Score" id
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- Step 3: Delete triples using the duplicate metric_id (44)
DELETE FROM task_dataset_metrics
WHERE metric_id = 44;

-- Step 4: Delete the duplicate metric
DELETE FROM metrics
WHERE id = 44 AND name = 'Score';

-- Verification queries
SELECT 'After consolidation:' AS status;

SELECT
    'Evaluations using score' AS check_type,
    COUNT(*) AS count
FROM evaluations
WHERE best_metric = 'score';

SELECT
    'Evaluations using Score (should be 0)' AS check_type,
    COUNT(*) AS count
FROM evaluations
WHERE best_metric = 'Score';

SELECT
    'Triples with score metric' AS check_type,
    COUNT(*) AS count
FROM task_dataset_metrics
WHERE metric_id = 43;

SELECT
    'Triples with Score metric (should be 0)' AS check_type,
    COUNT(*) AS count
FROM task_dataset_metrics
WHERE metric_id = 44;

SELECT
    'Score metric exists (should be 0)' AS check_type,
    COUNT(*) AS count
FROM metrics
WHERE id = 44;

COMMIT;
