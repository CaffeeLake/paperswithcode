-- Rollback Migration: Remove keywords column from methods table
-- Description: Removes the keywords TEXT field from the methods table
-- Date: 2025-10-13

-- Drop the index first
DROP INDEX IF EXISTS idx_methods_keywords;

-- Remove keywords column from methods table
ALTER TABLE methods DROP COLUMN IF EXISTS keywords;

-- Verify the rollback
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM
    information_schema.columns
WHERE
    table_name = 'methods';
