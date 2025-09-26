-- Migration: Add num_stars_updated_at column to repositories table
-- This enables proper tracking of when GitHub star counts were last updated
-- Date: 2025-09-26
-- Purpose: Support for GitHub stars update cron job

-- Check if the column already exists before adding it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'repositories'
        AND column_name = 'num_stars_updated_at'
    ) THEN
        -- Add the num_stars_updated_at column
        ALTER TABLE repositories
        ADD COLUMN num_stars_updated_at TIMESTAMP WITH TIME ZONE;

        RAISE NOTICE 'Added num_stars_updated_at column to repositories table';
    ELSE
        RAISE NOTICE 'Column num_stars_updated_at already exists in repositories table';
    END IF;
END $$;

-- Create index for better performance (only if it doesn't exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'repositories'
        AND indexname = 'idx_repositories_num_stars_updated_at'
    ) THEN
        CREATE INDEX idx_repositories_num_stars_updated_at ON repositories(num_stars_updated_at);
        RAISE NOTICE 'Created index idx_repositories_num_stars_updated_at';
    ELSE
        RAISE NOTICE 'Index idx_repositories_num_stars_updated_at already exists';
    END IF;
END $$;

-- Verify the migration was successful
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'repositories'
AND column_name = 'num_stars_updated_at';

-- Show current repositories table structure
\d repositories;
