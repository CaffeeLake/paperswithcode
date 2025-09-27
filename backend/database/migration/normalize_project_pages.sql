-- Migration script to normalize the project_pages table
-- This script removes the paper_id column from project_pages and creates a
-- paper_project_pages junction table to model the many-to-many relationship

-- =============================================================================
-- SECTION 1: CREATE JUNCTION TABLE
-- =============================================================================

-- Create the paper_project_pages junction table
CREATE TABLE IF NOT EXISTS paper_project_pages (
    paper_id BIGINT NOT NULL,
    project_page_id BIGINT NOT NULL,

    -- Metadata for the relationship
    is_official BOOLEAN DEFAULT FALSE,  -- Whether this is an official project page by paper authors
    source VARCHAR(50) DEFAULT 'migration', -- Source of this relationship
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Primary key is composite
    PRIMARY KEY (paper_id, project_page_id),

    -- Foreign key constraints
    CONSTRAINT fk_paper_project_pages_paper_id
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_project_pages_project_page_id
        FOREIGN KEY (project_page_id) REFERENCES project_pages(id) ON DELETE CASCADE
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_paper_project_pages_paper_id ON paper_project_pages(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_project_pages_project_page_id ON paper_project_pages(project_page_id);
CREATE INDEX IF NOT EXISTS idx_paper_project_pages_source ON paper_project_pages(source);

-- =============================================================================
-- SECTION 2: MIGRATE EXISTING DATA
-- =============================================================================

-- Migrate existing relationships from project_pages.paper_id to the junction table
-- Only migrate rows where paper_id is not null
INSERT INTO paper_project_pages (paper_id, project_page_id, is_official, source, created_at, updated_at)
SELECT
    pp.paper_id,
    pp.id as project_page_id,
    pp.is_official,
    COALESCE(pp.source, 'migration') as source,
    pp.created_at,
    pp.updated_at
FROM project_pages pp
WHERE pp.paper_id IS NOT NULL
ON CONFLICT (paper_id, project_page_id) DO NOTHING; -- Handle any potential duplicates

-- =============================================================================
-- SECTION 3: VERIFICATION
-- =============================================================================

-- Verify the migration was successful
DO $$
DECLARE
    original_count INTEGER;
    migrated_count INTEGER;
BEGIN
    -- Count original relationships
    SELECT COUNT(*) INTO original_count
    FROM project_pages
    WHERE paper_id IS NOT NULL;

    -- Count migrated relationships
    SELECT COUNT(*) INTO migrated_count
    FROM paper_project_pages;

    -- Report results
    RAISE NOTICE 'Migration verification:';
    RAISE NOTICE '  Original relationships: %', original_count;
    RAISE NOTICE '  Migrated relationships: %', migrated_count;

    -- Check if migration was complete
    IF original_count = migrated_count THEN
        RAISE NOTICE '  ✓ Migration completed successfully - all relationships migrated';
    ELSE
        RAISE WARNING '  ⚠ Migration incomplete - % relationships missing', (original_count - migrated_count);
    END IF;
END $$;

-- =============================================================================
-- SECTION 4: REMOVE PAPER_ID COLUMN FROM PROJECT_PAGES
-- =============================================================================

-- Drop the foreign key constraint first (if it exists)
DO $$
BEGIN
    -- Check if the constraint exists and drop it
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'project_pages_paper_id_fkey'
        AND table_name = 'project_pages'
    ) THEN
        ALTER TABLE project_pages DROP CONSTRAINT project_pages_paper_id_fkey;
        RAISE NOTICE 'Dropped foreign key constraint project_pages_paper_id_fkey';
    END IF;
END $$;

-- Drop any indexes on paper_id column
DROP INDEX IF EXISTS idx_project_pages_paper_id;

-- Remove the paper_id column
ALTER TABLE project_pages DROP COLUMN IF EXISTS paper_id;

-- =============================================================================
-- SECTION 5: UPDATE TABLE COMMENTS
-- =============================================================================

-- Update table comments to reflect the new structure
COMMENT ON TABLE project_pages IS 'Project pages showcasing paper work (demo sites, project websites) - normalized without direct paper reference';
COMMENT ON COLUMN project_pages.id IS 'Primary key for project page';
COMMENT ON COLUMN project_pages.url IS 'Full URL to project page';
COMMENT ON COLUMN project_pages.is_official IS 'Whether this is an official project page by paper authors (deprecated - use paper_project_pages.is_official)';
COMMENT ON COLUMN project_pages.source IS 'Source of the project page data: pwc_archive, ai_extraction, hf_api, manual, etc.';

COMMENT ON TABLE paper_project_pages IS 'Junction table for many-to-many relationship between papers and project pages';
COMMENT ON COLUMN paper_project_pages.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN paper_project_pages.project_page_id IS 'Foreign key reference to project_pages table';
COMMENT ON COLUMN paper_project_pages.is_official IS 'Whether this is an official project page by paper authors';
COMMENT ON COLUMN paper_project_pages.source IS 'Source of this relationship: migration, ai_extraction, manual, etc.';

-- =============================================================================
-- SECTION 6: FINAL STATISTICS
-- =============================================================================

-- Show final statistics
SELECT
    'NORMALIZATION COMPLETE' as status,
    (SELECT COUNT(*) FROM project_pages) as total_project_pages,
    (SELECT COUNT(*) FROM paper_project_pages) as total_relationships,
    (SELECT COUNT(DISTINCT paper_id) FROM paper_project_pages) as papers_with_project_pages,
    (SELECT COUNT(DISTINCT project_page_id) FROM paper_project_pages) as project_pages_with_papers;

-- Show sample relationships
SELECT
    'SAMPLE RELATIONSHIPS' as info,
    p.id as paper_id,
    p.title,
    pp.id as project_page_id,
    pp.url,
    ppp.is_official,
    ppp.source
FROM papers p
JOIN paper_project_pages ppp ON p.id = ppp.paper_id
JOIN project_pages pp ON ppp.project_page_id = pp.id
LIMIT 3;

-- Migration completed successfully
-- The project_pages table no longer has a paper_id column.
-- Use the paper_project_pages junction table to query relationships between papers and project pages.
