-- Migration: Drop dataset_metrics table after migration to task_dataset_metrics
-- Run this AFTER code has been deployed and tested with the new schema
--
-- Created: November 2025
-- Usage: psql -U postgres -d paperswithcode_hf -f backend/database/migration/drop_dataset_metrics.sql

-- Step 1: Drop the compatibility view
DROP VIEW IF EXISTS dataset_metrics_compat;

-- Step 2: Drop indexes on dataset_metrics
DROP INDEX IF EXISTS idx_dataset_metrics_dataset_id;
DROP INDEX IF EXISTS idx_dataset_metrics_metric_id;

-- Step 3: Drop the dataset_metrics table
DROP TABLE IF EXISTS dataset_metrics;

-- Note: This is a destructive operation. Ensure:
-- 1. Code has been updated to use task_dataset_metrics
-- 2. All API endpoints have been updated
-- 3. Backward compatibility period has passed
-- 4. Backup of dataset_metrics has been taken if needed
