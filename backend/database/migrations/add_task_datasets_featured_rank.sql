-- Migration: Add task_datasets display metadata table
-- Description: Stores task-specific benchmark membership and featured ordering.
-- Date: 2026-05-09

CREATE TABLE IF NOT EXISTS task_datasets (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    featured_rank INTEGER NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id, dataset_id),
    CONSTRAINT task_datasets_featured_rank_positive
        CHECK (featured_rank IS NULL OR featured_rank > 0)
);

ALTER TABLE task_datasets
ADD COLUMN IF NOT EXISTS featured_rank INTEGER NULL;

ALTER TABLE task_datasets
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE task_datasets
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'task_datasets_featured_rank_positive'
    ) THEN
        ALTER TABLE task_datasets
        ADD CONSTRAINT task_datasets_featured_rank_positive
        CHECK (featured_rank IS NULL OR featured_rank > 0);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_task_datasets_featured_rank
    ON task_datasets (task_id, featured_rank)
    WHERE featured_rank IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_task_datasets_task_id
    ON task_datasets(task_id);

CREATE INDEX IF NOT EXISTS idx_task_datasets_dataset_id
    ON task_datasets(dataset_id);

INSERT INTO task_datasets (task_id, dataset_id)
SELECT DISTINCT task_id, dataset_id
FROM task_dataset_metrics
ON CONFLICT (task_id, dataset_id) DO NOTHING;

WITH ranked(slug, rank) AS (
    VALUES
        ('swe-bench-pro', 1),
        ('swe-bench-verified', 2),
        ('swe-bench-multilingual', 3),
        ('scicode', 4),
        ('livecodebench', 5)
)
UPDATE task_datasets td
SET featured_rank = ranked.rank,
    updated_at = CURRENT_TIMESTAMP
FROM tasks t, datasets d, ranked
WHERE td.task_id = t.id
  AND td.dataset_id = d.id
  AND ranked.slug = d.slug
  AND t.slug = 'coding-agents';

COMMENT ON TABLE task_datasets IS
'Task-specific dataset membership and display metadata; metric definitions remain in task_dataset_metrics.';
COMMENT ON COLUMN task_datasets.featured_rank IS
'Optional task-specific featured ordering rank for benchmark display.';
