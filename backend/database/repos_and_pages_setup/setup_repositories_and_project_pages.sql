-- Comprehensive setup script for REPOSITORIES and PROJECT_PAGES tables
-- This script consolidates table creation, field additions, duplicate cleanup, and constraints
-- Can be run multiple times safely (idempotent operations)

-- =============================================================================
-- SECTION 1: TABLE CREATION
-- =============================================================================

-- REPOSITORIES - GitHub repositories linked to papers
CREATE TABLE IF NOT EXISTS repositories (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'unknown',   -- Source of the repository data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PROJECT_PAGES - Project pages showcasing paper work (demo sites, project websites)
CREATE TABLE IF NOT EXISTS project_pages (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE, -- Created by the paper authors
    source VARCHAR(50) DEFAULT 'unknown',   -- Source of the project page data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- SECTION 2: ADD SOURCE FIELDS (for existing tables without source columns)
-- =============================================================================

-- Add source field to repositories table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'repositories' AND column_name = 'source'
    ) THEN
        ALTER TABLE repositories ADD COLUMN source VARCHAR(50) DEFAULT 'unknown';
    END IF;
END $$;

-- Add source field to project_pages table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'project_pages' AND column_name = 'source'
    ) THEN
        ALTER TABLE project_pages ADD COLUMN source VARCHAR(50) DEFAULT 'unknown';
    END IF;
END $$;

-- =============================================================================
-- SECTION 3: INDEXES FOR PERFORMANCE
-- =============================================================================

-- Repositories indexes
CREATE INDEX IF NOT EXISTS idx_repositories_paper_id ON repositories(paper_id);
CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);
CREATE INDEX IF NOT EXISTS idx_repositories_stars ON repositories(num_stars DESC);
CREATE INDEX IF NOT EXISTS idx_repositories_owner ON repositories(owner);
CREATE INDEX IF NOT EXISTS idx_repositories_name ON repositories(name);
CREATE INDEX IF NOT EXISTS idx_repositories_source ON repositories(source);

-- Project pages indexes
CREATE INDEX IF NOT EXISTS idx_project_pages_paper_id ON project_pages(paper_id);
CREATE INDEX IF NOT EXISTS idx_project_pages_url ON project_pages(url);
CREATE INDEX IF NOT EXISTS idx_project_pages_source ON project_pages(source);

-- =============================================================================
-- SECTION 4: TRIGGERS FOR UPDATED_AT COLUMNS
-- =============================================================================

-- Create or replace the update function if it doesn't exist
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers for updated_at columns
DROP TRIGGER IF EXISTS update_repositories_updated_at ON repositories;
CREATE TRIGGER update_repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_project_pages_updated_at ON project_pages;
CREATE TRIGGER update_project_pages_updated_at
    BEFORE UPDATE ON project_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SECTION 5: DUPLICATE CLEANUP AND CONSTRAINTS
-- =============================================================================

-- Show statistics before cleanup
SELECT
    'BEFORE CLEANUP' as stage,
    'repositories' as table_name,
    COUNT(*) as total_entries,
    COUNT(DISTINCT (paper_id, url)) as unique_combinations
FROM repositories
UNION ALL
SELECT
    'BEFORE CLEANUP' as stage,
    'project_pages' as table_name,
    COUNT(*) as total_entries,
    COUNT(DISTINCT (paper_id, url)) as unique_combinations
FROM project_pages;

-- Clean up duplicate repositories
-- Step 1: Handle URL normalization (remove trailing slashes)
WITH repo_url_variations AS (
    SELECT
        paper_id,
        RTRIM(url, '/') as normalized_url,
        MIN(id) as keep_id,
        array_agg(id ORDER BY created_at) as all_ids,
        COUNT(*) as variation_count
    FROM repositories
    GROUP BY paper_id, RTRIM(url, '/')
    HAVING COUNT(*) > 1
)
DELETE FROM repositories
WHERE id IN (
    SELECT unnest(all_ids[2:])
    FROM repo_url_variations
);

-- Step 2: Remove exact duplicates (same paper_id and url)
WITH repo_duplicates AS (
    SELECT
        paper_id,
        url,
        MIN(id) as keep_id,
        array_agg(id ORDER BY created_at) as all_ids,
        COUNT(*) as duplicate_count
    FROM repositories
    GROUP BY paper_id, url
    HAVING COUNT(*) > 1
)
DELETE FROM repositories
WHERE id IN (
    SELECT unnest(all_ids[2:])
    FROM repo_duplicates
);

-- Clean up duplicate project pages
-- Step 1: Handle URL normalization (remove trailing slashes)
WITH page_url_variations AS (
    SELECT
        paper_id,
        RTRIM(url, '/') as normalized_url,
        MIN(id) as keep_id,
        array_agg(id ORDER BY created_at) as all_ids,
        COUNT(*) as variation_count
    FROM project_pages
    GROUP BY paper_id, RTRIM(url, '/')
    HAVING COUNT(*) > 1
)
DELETE FROM project_pages
WHERE id IN (
    SELECT unnest(all_ids[2:])
    FROM page_url_variations
);

-- Step 2: Remove exact duplicates (same paper_id and url)
WITH page_duplicates AS (
    SELECT
        paper_id,
        url,
        MIN(id) as keep_id,
        array_agg(id ORDER BY created_at) as all_ids,
        COUNT(*) as duplicate_count
    FROM project_pages
    GROUP BY paper_id, url
    HAVING COUNT(*) > 1
)
DELETE FROM project_pages
WHERE id IN (
    SELECT unnest(all_ids[2:])
    FROM page_duplicates
);

-- Add unique constraints to prevent future duplicates
-- Note: These will fail gracefully if constraints already exist
DO $$
BEGIN
    -- Add unique constraint for repositories
    BEGIN
        ALTER TABLE repositories
        ADD CONSTRAINT unique_paper_repository
        UNIQUE (paper_id, url);
    EXCEPTION
        WHEN duplicate_table THEN
            -- Constraint already exists, continue
            NULL;
    END;

    -- Add unique constraint for project_pages
    BEGIN
        ALTER TABLE project_pages
        ADD CONSTRAINT unique_paper_project_page
        UNIQUE (paper_id, url);
    EXCEPTION
        WHEN duplicate_table THEN
            -- Constraint already exists, continue
            NULL;
    END;
END $$;

-- =============================================================================
-- SECTION 6: DATA MIGRATION (Update legacy data sources)
-- =============================================================================

-- Update existing repositories to 'pwc_archive' if they have unknown source
UPDATE repositories
SET source = 'pwc_archive'
WHERE source = 'unknown' OR source IS NULL;

-- Update existing project_pages to 'pwc_archive' if they have unknown source
UPDATE project_pages
SET source = 'pwc_archive'
WHERE source = 'unknown' OR source IS NULL;

-- =============================================================================
-- SECTION 7: TABLE DOCUMENTATION
-- =============================================================================

-- Add comments for documentation
COMMENT ON TABLE repositories IS 'GitHub repositories linked to papers';
COMMENT ON COLUMN repositories.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN repositories.url IS 'Full GitHub repository URL';
COMMENT ON COLUMN repositories.owner IS 'GitHub username/organization that owns the repository';
COMMENT ON COLUMN repositories.name IS 'Repository name';
COMMENT ON COLUMN repositories.num_stars IS 'Number of GitHub stars (to be populated later)';
COMMENT ON COLUMN repositories.is_official IS 'Whether this is the official repository by paper authors';
COMMENT ON COLUMN repositories.source IS 'Source of the repository data: pwc_archive, ai_extraction, hf_api, manual, etc.';

COMMENT ON TABLE project_pages IS 'Project pages showcasing paper work (demo sites, project websites)';
COMMENT ON COLUMN project_pages.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN project_pages.url IS 'Full URL to project page';
COMMENT ON COLUMN project_pages.is_official IS 'Whether this is an official project page by paper authors';
COMMENT ON COLUMN project_pages.source IS 'Source of the project page data: pwc_archive, ai_extraction, hf_api, manual, etc.';

-- =============================================================================
-- SECTION 8: FINAL STATISTICS AND VERIFICATION
-- =============================================================================

-- Show statistics after cleanup
SELECT
    'AFTER CLEANUP' as stage,
    'repositories' as table_name,
    COUNT(*) as total_entries,
    COUNT(DISTINCT (paper_id, url)) as unique_combinations,
    COUNT(*) - COUNT(DISTINCT (paper_id, url)) as duplicates_eliminated
FROM repositories
UNION ALL
SELECT
    'AFTER CLEANUP' as stage,
    'project_pages' as table_name,
    COUNT(*) as total_entries,
    COUNT(DISTINCT (paper_id, url)) as unique_combinations,
    COUNT(*) - COUNT(DISTINCT (paper_id, url)) as duplicates_eliminated
FROM project_pages;

-- Check for any remaining duplicates (should be 0)
SELECT
    'REMAINING DUPLICATES CHECK' as info,
    'repositories' as table_name,
    paper_id,
    url,
    COUNT(*) as duplicate_count
FROM repositories
GROUP BY paper_id, url
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 5;

SELECT
    'REMAINING DUPLICATES CHECK' as info,
    'project_pages' as table_name,
    paper_id,
    url,
    COUNT(*) as duplicate_count
FROM project_pages
GROUP BY paper_id, url
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 5;

-- Show constraint information
SELECT
    'CONSTRAINTS VERIFICATION' as info,
    conname as constraint_name,
    contype as constraint_type,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid IN ('repositories'::regclass, 'project_pages'::regclass)
AND contype = 'u'  -- unique constraints only
ORDER BY conrelid::regclass::text, conname;

-- =============================================================================
-- SCRIPT COMPLETION MESSAGE
-- =============================================================================

SELECT
    '✅ SETUP COMPLETE' as status,
    'Repositories and Project Pages tables are ready' as message,
    'Tables created, duplicates cleaned, constraints added' as details;
