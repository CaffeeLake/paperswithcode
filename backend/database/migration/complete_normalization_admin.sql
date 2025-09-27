-- Final step of project_pages normalization - requires database admin privileges
-- This script completes the normalization by replacing the original table with the normalized one

-- =============================================================================
-- VERIFICATION BEFORE FINAL STEP
-- =============================================================================

-- Verify that the migration was successful
DO $$
DECLARE
    original_count INTEGER;
    normalized_count INTEGER;
    junction_count INTEGER;
BEGIN
    -- Check counts
    SELECT COUNT(*) INTO original_count FROM project_pages;
    SELECT COUNT(*) INTO normalized_count FROM project_pages_normalized;
    SELECT COUNT(*) INTO junction_count FROM paper_project_pages;

    RAISE NOTICE 'Pre-finalization verification:';
    RAISE NOTICE '  Original project_pages: %', original_count;
    RAISE NOTICE '  Normalized project_pages: %', normalized_count;
    RAISE NOTICE '  Junction relationships: %', junction_count;

    -- Verify data integrity
    IF normalized_count != original_count THEN
        RAISE EXCEPTION 'Data count mismatch! Original: %, Normalized: %', original_count, normalized_count;
    END IF;

    IF junction_count = 0 THEN
        RAISE EXCEPTION 'No relationships found in junction table!';
    END IF;

    RAISE NOTICE '✅ Verification passed - ready to finalize';
END $$;

-- =============================================================================
-- BACKUP ORIGINAL TABLE
-- =============================================================================

-- Create a final backup before dropping the original table
DROP TABLE IF EXISTS project_pages_original_backup;
CREATE TABLE project_pages_original_backup AS SELECT * FROM project_pages;

-- =============================================================================
-- FINALIZE NORMALIZATION
-- =============================================================================

-- Drop the original table
DROP TABLE project_pages CASCADE;

-- Rename the normalized table to the original name
ALTER TABLE project_pages_normalized RENAME TO project_pages;

-- Recreate the foreign key constraint in the junction table
ALTER TABLE paper_project_pages
DROP CONSTRAINT IF EXISTS fk_paper_project_pages_project_page_id;

ALTER TABLE paper_project_pages
ADD CONSTRAINT fk_paper_project_pages_project_page_id
    FOREIGN KEY (project_page_id) REFERENCES project_pages(id) ON DELETE CASCADE;

-- =============================================================================
-- UPDATE TABLE COMMENTS
-- =============================================================================

COMMENT ON TABLE project_pages IS 'Project pages showcasing paper work (demo sites, project websites) - normalized without direct paper reference';
COMMENT ON COLUMN project_pages.id IS 'Primary key for project page';
COMMENT ON COLUMN project_pages.url IS 'Full URL to project page';
COMMENT ON COLUMN project_pages.is_official IS 'Whether this is an official project page by paper authors (use paper_project_pages.is_official for relationship-specific data)';
COMMENT ON COLUMN project_pages.source IS 'Source of the project page data: pwc_archive, ai_extraction, hf_api, manual, etc.';

-- =============================================================================
-- CREATE INDEXES FOR PERFORMANCE
-- =============================================================================

-- Recreate indexes on the new project_pages table
CREATE INDEX IF NOT EXISTS idx_project_pages_url ON project_pages(url);
CREATE INDEX IF NOT EXISTS idx_project_pages_source ON project_pages(source);
CREATE INDEX IF NOT EXISTS idx_project_pages_is_official ON project_pages(is_official);

-- =============================================================================
-- FINAL VERIFICATION
-- =============================================================================

DO $$
DECLARE
    pages_count INTEGER;
    relationships_count INTEGER;
    sample_count INTEGER;
BEGIN
    -- Final counts
    SELECT COUNT(*) INTO pages_count FROM project_pages;
    SELECT COUNT(*) INTO relationships_count FROM paper_project_pages;

    -- Test a sample join
    SELECT COUNT(*) INTO sample_count
    FROM papers p
    JOIN paper_project_pages ppp ON p.id = ppp.paper_id
    JOIN project_pages pp ON ppp.project_page_id = pp.id
    LIMIT 10;

    RAISE NOTICE 'Final verification:';
    RAISE NOTICE '  Project pages: %', pages_count;
    RAISE NOTICE '  Relationships: %', relationships_count;
    RAISE NOTICE '  Sample join test: % rows', sample_count;

    IF sample_count > 0 THEN
        RAISE NOTICE '✅ Normalization completed successfully!';
        RAISE NOTICE '✅ The project_pages table is now normalized';
        RAISE NOTICE '✅ Use paper_project_pages junction table for relationships';
    ELSE
        RAISE EXCEPTION 'Final verification failed - joins not working!';
    END IF;
END $$;

-- =============================================================================
-- SHOW FINAL STATISTICS
-- =============================================================================

SELECT
    'NORMALIZATION COMPLETE' as status,
    (SELECT COUNT(*) FROM project_pages) as total_project_pages,
    (SELECT COUNT(*) FROM paper_project_pages) as total_relationships,
    (SELECT COUNT(DISTINCT paper_id) FROM paper_project_pages) as papers_with_project_pages,
    (SELECT COUNT(DISTINCT project_page_id) FROM paper_project_pages) as project_pages_with_papers;

-- Show sample of the new structure
SELECT
    'SAMPLE NORMALIZED STRUCTURE' as info,
    p.id as paper_id,
    p.title,
    pp.id as project_page_id,
    pp.url,
    ppp.is_official,
    ppp.source
FROM papers p
JOIN paper_project_pages ppp ON p.id = ppp.paper_id
JOIN project_pages pp ON ppp.project_page_id = pp.id
LIMIT 5;
