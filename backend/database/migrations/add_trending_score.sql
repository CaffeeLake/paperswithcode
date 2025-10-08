-- Migration: Add trending score fields to repositories table
-- Date: 2025-10-08
-- Description: Adds EMA-based trending score tracking to repositories

-- Add trending_score column (stores stars per hour as NUMERIC for precision)
ALTER TABLE repositories
ADD COLUMN IF NOT EXISTS trending_score NUMERIC(10, 4) NULL;

COMMENT ON COLUMN repositories.trending_score IS 'EMA trending score (stars/hour)';

-- Add trending_score_updated_at column (tracks when trending score was last calculated)
ALTER TABLE repositories
ADD COLUMN IF NOT EXISTS trending_score_updated_at TIMESTAMP WITH TIME ZONE NULL;

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_repositories_trending_score
ON repositories(trending_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_repositories_trending_score_updated_at
ON repositories(trending_score_updated_at);

-- Create composite index for trending queries (papers with high scores that need refresh)
CREATE INDEX IF NOT EXISTS idx_repositories_trending_refresh
ON repositories(trending_score_updated_at NULLS FIRST, trending_score DESC NULLS LAST);

-- Verify the changes
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'repositories'
        AND column_name = 'trending_score'
    ) THEN
        RAISE NOTICE 'Column trending_score added successfully';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'repositories'
        AND column_name = 'trending_score_updated_at'
    ) THEN
        RAISE NOTICE 'Column trending_score_updated_at added successfully';
    END IF;
END $$;
