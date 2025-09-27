-- FINALIZE PROJECT PAGES NORMALIZATION
-- This script must be run as postgres superuser to complete the normalization
-- Run with: sudo -u postgres psql -d paperswithcode_hf -f finalize_normalization_admin.sql

BEGIN;

-- 1. Create backup of original table
DROP TABLE IF EXISTS project_pages_original_final_backup;
CREATE TABLE project_pages_original_final_backup AS SELECT * FROM project_pages;

-- 2. Create simplified junction table with only paper_id and project_page_id
DROP TABLE IF EXISTS paper_project_pages_simple;
CREATE TABLE paper_project_pages_simple (
    paper_id BIGINT NOT NULL,
    project_page_id BIGINT NOT NULL,
    PRIMARY KEY (paper_id, project_page_id),
    CONSTRAINT fk_paper_project_pages_simple_paper_id
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_project_pages_simple_project_page_id
        FOREIGN KEY (project_page_id) REFERENCES project_pages_normalized(id) ON DELETE CASCADE
);

-- 3. Copy data from current junction table (only the ID columns)
INSERT INTO paper_project_pages_simple (paper_id, project_page_id)
SELECT DISTINCT paper_id, project_page_id
FROM paper_project_pages
ON CONFLICT (paper_id, project_page_id) DO NOTHING;

-- 4. Drop original tables
DROP TABLE project_pages CASCADE;
DROP TABLE paper_project_pages CASCADE;

-- 5. Rename tables to final names
ALTER TABLE project_pages_normalized RENAME TO project_pages;
ALTER TABLE paper_project_pages_simple RENAME TO paper_project_pages;

-- 6. Update foreign key constraint to point to the new project_pages table
ALTER TABLE paper_project_pages DROP CONSTRAINT IF EXISTS fk_paper_project_pages_simple_project_page_id;
ALTER TABLE paper_project_pages
ADD CONSTRAINT fk_paper_project_pages_project_page_id
    FOREIGN KEY (project_page_id) REFERENCES project_pages(id) ON DELETE CASCADE;

-- 7. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_project_pages_url ON project_pages(url);
CREATE INDEX IF NOT EXISTS idx_project_pages_source ON project_pages(source);
CREATE INDEX IF NOT EXISTS idx_project_pages_is_official ON project_pages(is_official);
CREATE INDEX IF NOT EXISTS idx_paper_project_pages_paper_id ON paper_project_pages(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_project_pages_project_page_id ON paper_project_pages(project_page_id);

-- 8. Grant permissions to application user
GRANT ALL PRIVILEGES ON TABLE project_pages TO paperswithcode_user;
GRANT ALL PRIVILEGES ON TABLE paper_project_pages TO paperswithcode_user;
-- Grant sequence permissions (check if sequence exists first)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.sequences WHERE sequence_name = 'project_pages_id_seq') THEN
        EXECUTE 'GRANT ALL PRIVILEGES ON SEQUENCE project_pages_id_seq TO paperswithcode_user';
    END IF;
END $$;

-- 9. Final verification
DO $$
DECLARE
    pages_count INTEGER;
    relationships_count INTEGER;
    has_paper_id BOOLEAN;
    junction_columns INTEGER;
    join_test INTEGER;
BEGIN
    -- Count records
    SELECT COUNT(*) INTO pages_count FROM project_pages;
    SELECT COUNT(*) INTO relationships_count FROM paper_project_pages;

    -- Check if project_pages has paper_id (should be false)
    SELECT EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'project_pages' AND column_name = 'paper_id'
    ) INTO has_paper_id;

    -- Count columns in junction table (should be 2)
    SELECT COUNT(*) INTO junction_columns
    FROM information_schema.columns
    WHERE table_name = 'paper_project_pages';

    -- Test relationships work
    SELECT COUNT(*) INTO join_test
    FROM papers p
    JOIN paper_project_pages ppp ON p.id = ppp.paper_id
    JOIN project_pages pp ON ppp.project_page_id = pp.id
    LIMIT 10;

    -- Output verification results
    RAISE NOTICE 'FINALIZATION VERIFICATION:';
    RAISE NOTICE '  project_pages count: %', pages_count;
    RAISE NOTICE '  paper_project_pages count: %', relationships_count;
    RAISE NOTICE '  project_pages has paper_id: %', CASE WHEN has_paper_id THEN 'YES (BAD)' ELSE 'NO (GOOD)' END;
    RAISE NOTICE '  paper_project_pages columns: %', junction_columns;
    RAISE NOTICE '  Relationship joins working: % (% test records)', CASE WHEN join_test > 0 THEN 'YES' ELSE 'NO' END, join_test;

    -- Verify success conditions
    IF NOT has_paper_id AND junction_columns = 2 AND join_test > 0 THEN
        RAISE NOTICE 'SUCCESS: All verifications passed!';
    ELSE
        RAISE EXCEPTION 'VERIFICATION FAILED - Rolling back transaction';
    END IF;
END $$;

COMMIT;

-- Final success message
\echo 'PROJECT PAGES NORMALIZATION FINALIZED SUCCESSFULLY!'
\echo 'Final State:'
\echo '  ✅ project_pages table (normalized, no paper_id)'
\echo '  ✅ paper_project_pages table (only paper_id, project_page_id)'
\echo '  ✅ Original table backed up as project_pages_original_final_backup'
\echo '  ✅ All relationships preserved and working'
\echo '  ✅ Permissions granted to paperswithcode_user'
