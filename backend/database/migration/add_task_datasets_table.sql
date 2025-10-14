-- Add task_datasets junction table for many-to-many relationship between tasks and datasets
-- This allows datasets like ImageNet to be directly linked to tasks like "Image Classification"
-- Migration created: October 2025

-- Create the task_datasets junction table
CREATE TABLE IF NOT EXISTS task_datasets (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,

    -- Composite primary key
    PRIMARY KEY (task_id, dataset_id)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_task_datasets_task_id ON task_datasets(task_id);
CREATE INDEX IF NOT EXISTS idx_task_datasets_dataset_id ON task_datasets(dataset_id);

-- Add comments for documentation
COMMENT ON TABLE task_datasets IS 'Junction table linking datasets to their associated tasks (e.g., ImageNet -> Image Classification)';
COMMENT ON COLUMN task_datasets.task_id IS 'Foreign key to tasks table';
COMMENT ON COLUMN task_datasets.dataset_id IS 'Foreign key to datasets table';
