-- Migration: Add keywords column to methods table
-- Description: Adds a keywords TEXT field to the methods table to store comma-separated keywords
-- Date: 2025-10-13

-- Add keywords column to methods table
ALTER TABLE methods ADD COLUMN IF NOT EXISTS keywords TEXT;

-- Add comment to the column
COMMENT ON COLUMN methods.keywords IS 'Comma-separated keywords for matching papers to this method';

-- Create an index on keywords for better search performance
CREATE INDEX IF NOT EXISTS idx_methods_keywords ON methods USING gin (to_tsvector('english', COALESCE(keywords, '')));

-- Verify the migration
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM
    information_schema.columns
WHERE
    table_name = 'methods'
    AND column_name = 'keywords';
