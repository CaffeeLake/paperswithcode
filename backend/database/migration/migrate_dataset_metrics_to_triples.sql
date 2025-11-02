-- Migration: Backfill task_dataset_metrics from dataset_metrics and evaluations
-- This populates the new leaderboard triples table from existing data
--
-- Created: November 2025
-- Usage: psql -U postgres -d paperswithcode_hf -f backend/database/migration/migrate_dataset_metrics_to_triples.sql

-- Step 1: Insert triples from dataset_metrics × task_datasets
-- For each dataset-metric pair, create a triple for every task linked to that dataset
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT DISTINCT
    td.task_id,
    dm.dataset_id,
    dm.metric_id,
    CURRENT_TIMESTAMP
FROM dataset_metrics dm
INNER JOIN task_datasets td ON dm.dataset_id = td.dataset_id
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- Step 2: Insert missing triples implied by existing evaluations
-- If an evaluation uses a metric not yet in task_dataset_metrics, add it
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT DISTINCT
    e.task_id,
    e.dataset_id,
    m.id AS metric_id,
    CURRENT_TIMESTAMP
FROM evaluations e
INNER JOIN metrics m ON e.best_metric = m.name
WHERE e.best_metric IS NOT NULL
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- Step 3: Add composite index on evaluations for efficient leaderboard queries
CREATE INDEX IF NOT EXISTS idx_evaluations_task_dataset_metric
ON evaluations(task_id, dataset_id, best_metric);

-- Step 4: Create compatibility view for backward compatibility (optional, for one release)
CREATE OR REPLACE VIEW dataset_metrics_compat AS
SELECT DISTINCT
    tdm.dataset_id,
    tdm.metric_id,
    MIN(tdm.created_at) AS created_at
FROM task_dataset_metrics tdm
GROUP BY tdm.dataset_id, tdm.metric_id;

COMMENT ON VIEW dataset_metrics_compat IS 'Compatibility view for old dataset_metrics table. Shows all metrics allowed for a dataset across all tasks. DEPRECATED: Use task_dataset_metrics directly.';

-- Verification queries
-- Run these to verify the migration succeeded:

-- Count of triples created
-- SELECT COUNT(*) FROM task_dataset_metrics;

-- Triples for popular datasets
-- SELECT t.name AS task, d.name AS dataset, m.name AS metric
-- FROM task_dataset_metrics tdm
-- JOIN tasks t ON tdm.task_id = t.id
-- JOIN datasets d ON tdm.dataset_id = d.id
-- JOIN metrics m ON tdm.metric_id = m.id
-- WHERE d.name IN ('COCO', 'ImageNet', 'LibriSpeech')
-- ORDER BY d.name, t.name, m.name;

-- Evaluations without matching triples (should be 0 after migration)
-- SELECT COUNT(*)
-- FROM evaluations e
-- LEFT JOIN metrics m ON e.best_metric = m.name
-- LEFT JOIN task_dataset_metrics tdm ON (
--     e.task_id = tdm.task_id AND
--     e.dataset_id = tdm.dataset_id AND
--     m.id = tdm.metric_id
-- )
-- WHERE e.best_metric IS NOT NULL AND tdm.task_id IS NULL;
