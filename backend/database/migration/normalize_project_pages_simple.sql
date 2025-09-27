-- Simple migration script to normalize the project_pages table
-- This version works with limited permissions by using a different approach

-- =============================================================================
-- SECTION 1: CREATE JUNCTION TABLE
-- =============================================================================

-- Create the paper_project_pages junction table
CREATE TABLE IF NOT EXISTS paper_project_pages (
    paper_id BIGINT NOT NULL,
    project_page_id BIGINT NOT NULL,

    -- Metadata for the relationship
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'migration',
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
ON CONFLICT (paper_id, project_page_id) DO NOTHING;

-- =============================================================================
-- SECTION 3: CREATE NEW NORMALIZED PROJECT_PAGES TABLE
-- =============================================================================

-- Create the new normalized project_pages table without paper_id
CREATE TABLE IF NOT EXISTS project_pages_normalized (
    id BIGINT NOT NULL,  -- Keep the same IDs
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id)
);

-- Copy data from original table (excluding paper_id)
INSERT INTO project_pages_normalized (id, url, is_official, source, created_at, updated_at)
SELECT
    id,
    url,
    is_official,
    source,
    created_at,
    updated_at
FROM project_pages
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- SECTION 4: RENAME TABLES (REQUIRES MANUAL STEP)
-- =============================================================================

-- The following steps need to be done manually by a database administrator:
-- 1. DROP TABLE project_pages;
-- 2. ALTER TABLE project_pages_normalized RENAME TO project_pages;
-- 3. Update any sequences if needed

-- For now, we'll leave both tables and provide instructions

-- =============================================================================
-- SECTION 5: ADD COMMENTS
-- =============================================================================

COMMENT ON TABLE paper_project_pages IS 'Junction table for many-to-many relationship between papers and project pages';
COMMENT ON COLUMN paper_project_pages.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN paper_project_pages.project_page_id IS 'Foreign key reference to project_pages table';
COMMENT ON COLUMN paper_project_pages.is_official IS 'Whether this is an official project page by paper authors';
COMMENT ON COLUMN paper_project_pages.source IS 'Source of this relationship: migration, ai_extraction, manual, etc.';

COMMENT ON TABLE project_pages_normalized IS 'Normalized project pages table without direct paper reference (ready to replace project_pages)';

-- =============================================================================
-- SECTION 6: VERIFICATION QUERIES
-- =============================================================================

-- Show migration results
SELECT
    'MIGRATION RESULTS' as status,
    (SELECT COUNT(*) FROM project_pages) as original_project_pages,
    (SELECT COUNT(*) FROM project_pages_normalized) as normalized_project_pages,
    (SELECT COUNT(*) FROM paper_project_pages) as relationships_created,
    (SELECT COUNT(DISTINCT paper_id) FROM paper_project_pages) as papers_with_project_pages;

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
JOIN project_pages_normalized pp ON ppp.project_page_id = pp.id
LIMIT 5;
