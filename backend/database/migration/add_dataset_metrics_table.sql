-- Migration: Add dataset_metrics junction table
-- This establishes a many-to-many relationship between datasets and metrics
-- to enforce which metrics are valid for each dataset
--
-- Created: October 2025
-- Usage: psql -U postgres -d paperswithcode_hf -f backend/database/migration/add_dataset_metrics_table.sql

-- Create the dataset_metrics junction table
CREATE TABLE IF NOT EXISTS dataset_metrics (
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    metric_id BIGINT NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,

    -- Timestamps for tracking when the relationship was established
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Composite primary key ensures each dataset-metric pair is unique
    PRIMARY KEY (dataset_id, metric_id)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_dataset_metrics_dataset_id ON dataset_metrics(dataset_id);
CREATE INDEX IF NOT EXISTS idx_dataset_metrics_metric_id ON dataset_metrics(metric_id);

-- Add comments for documentation
COMMENT ON TABLE dataset_metrics IS 'Junction table linking datasets to their allowed evaluation metrics';
COMMENT ON COLUMN dataset_metrics.dataset_id IS 'Foreign key to datasets table';
COMMENT ON COLUMN dataset_metrics.metric_id IS 'Foreign key to metrics table';
COMMENT ON COLUMN dataset_metrics.created_at IS 'When this dataset-metric relationship was created';

-- Note: After creating this table, you should:
-- 1. Run scripts/export_dataset_metrics_template.py to generate a CSV
-- 2. Manually configure which metrics are allowed for each dataset
-- 3. Run scripts/import_dataset_metrics_from_csv.py to populate this table
-- 4. Run scripts/migrate_evaluation_metrics.py to fix existing evaluations
