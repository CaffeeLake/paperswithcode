-- Migration: Add task_dataset_metrics junction table
-- This establishes a many-to-many-to-many relationship between tasks, datasets, and metrics
-- to define leaderboards as triples (task, dataset, metric)
--
-- Created: November 2025
-- Usage: psql -U postgres -d paperswithcode_hf -f backend/database/migration/add_task_dataset_metrics_table.sql

-- Create the task_dataset_metrics junction table
CREATE TABLE IF NOT EXISTS task_dataset_metrics (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    metric_id BIGINT NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,

    -- Timestamps for tracking when the relationship was established
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Composite primary key ensures each (task, dataset, metric) triple is unique
    PRIMARY KEY (task_id, dataset_id, metric_id)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_task_dataset_metrics_task_id ON task_dataset_metrics(task_id);
CREATE INDEX IF NOT EXISTS idx_task_dataset_metrics_dataset_id ON task_dataset_metrics(dataset_id);
CREATE INDEX IF NOT EXISTS idx_task_dataset_metrics_metric_id ON task_dataset_metrics(metric_id);
CREATE INDEX IF NOT EXISTS idx_task_dataset_metrics_task_dataset ON task_dataset_metrics(task_id, dataset_id);

-- Add comments for documentation
COMMENT ON TABLE task_dataset_metrics IS 'Junction table defining leaderboards as (task, dataset, metric) triples';
COMMENT ON COLUMN task_dataset_metrics.task_id IS 'Foreign key to tasks table';
COMMENT ON COLUMN task_dataset_metrics.dataset_id IS 'Foreign key to datasets table';
COMMENT ON COLUMN task_dataset_metrics.metric_id IS 'Foreign key to metrics table';
COMMENT ON COLUMN task_dataset_metrics.created_at IS 'When this leaderboard triple was created';

-- Note: After creating this table, run migrate_dataset_metrics_to_triples.sql to populate it
