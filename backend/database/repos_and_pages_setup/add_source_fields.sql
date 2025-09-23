-- Add source fields to repositories and project_pages tables
-- This migration adds tracking for where the data came from

-- Add source field to repositories table
ALTER TABLE repositories
ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'unknown';

-- Add source field to project_pages table
ALTER TABLE project_pages
ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'unknown';

-- Add indexes for the new source fields
CREATE INDEX IF NOT EXISTS idx_repositories_source ON repositories(source);
CREATE INDEX IF NOT EXISTS idx_project_pages_source ON project_pages(source);

-- Add comments for documentation
COMMENT ON COLUMN repositories.source IS 'Source of the repository data: pwc_archive, ai_extraction, manual, etc.';
COMMENT ON COLUMN project_pages.source IS 'Source of the project page data: pwc_archive, ai_extraction, manual, etc.';

-- Update existing repositories to 'pwc_archive' (from legacy data)
-- We'll exclude the ones from AI extraction cache in a separate step
UPDATE repositories
SET source = 'pwc_archive'
WHERE source = 'unknown';

-- Update existing project_pages to 'pwc_archive' (from legacy data)
-- We'll exclude the ones from AI extraction cache in a separate step
UPDATE project_pages
SET source = 'pwc_archive'
WHERE source = 'unknown';
