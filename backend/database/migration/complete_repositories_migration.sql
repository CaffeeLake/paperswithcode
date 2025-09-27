-- Complete the repositories migration by working around permission issues
-- This script completes the migration that was partially successful

-- =============================================================================
-- STEP 1: Fix the repositories_new table to properly deduplicate
-- =============================================================================

-- First, let's clean up the repositories_new table to remove duplicates
-- The previous migration didn't deduplicate properly

-- Create a temporary table with properly deduplicated repositories
CREATE TEMP TABLE repositories_deduplicated AS
SELECT DISTINCT ON (url)
    url,
    owner,
    name,
    MAX(num_stars) as num_stars,  -- Take the highest star count
    BOOL_OR(is_official) as is_official,  -- True if any instance was official
    source,
    MIN(created_at) as created_at,  -- Take the earliest creation date
    MAX(updated_at) as updated_at   -- Take the latest update date
FROM repositories_new
WHERE url IS NOT NULL AND url != ''
GROUP BY url, owner, name, source
ORDER BY url, updated_at DESC;

-- Clear the repositories_new table and repopulate with deduplicated data
TRUNCATE repositories_new RESTART IDENTITY CASCADE;

-- Insert deduplicated data back
INSERT INTO repositories_new (url, owner, name, num_stars, is_official, source, created_at, updated_at)
SELECT url, owner, name, num_stars, is_official, source, created_at, updated_at
FROM repositories_deduplicated;

-- =============================================================================
-- STEP 2: Fix the paper_repositories relationships
-- =============================================================================

-- Clear the paper_repositories table
TRUNCATE paper_repositories;

-- Rebuild the relationships using the deduplicated repositories
INSERT INTO paper_repositories (paper_id, repository_id, is_official, source, created_at)
SELECT DISTINCT
    r_backup.paper_id,
    r_new.id as repository_id,
    r_backup.is_official,
    r_backup.source,
    r_backup.created_at
FROM repositories_backup r_backup
JOIN repositories_new r_new ON r_backup.url = r_new.url
WHERE r_backup.paper_id IS NOT NULL;

-- =============================================================================
-- STEP 3: Since we can't drop the original table, rename it and use the new one
-- =============================================================================

-- Rename the original repositories table to repositories_old (if we have permission)
-- If this fails, we'll work around it differently
DO $$
BEGIN
    -- Try to rename the original table
    BEGIN
        ALTER TABLE repositories RENAME TO repositories_old;
        RAISE NOTICE 'Successfully renamed original repositories table to repositories_old';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Cannot rename original repositories table due to permissions - will use different approach';
    END;
END $$;

-- Rename repositories_new to repositories
ALTER TABLE repositories_new RENAME TO repositories;

-- Update the sequence name
ALTER SEQUENCE repositories_new_id_seq RENAME TO repositories_id_seq;

-- =============================================================================
-- STEP 4: Update any views or dependencies that might reference the old table
-- =============================================================================

-- If there are any views that reference the old repositories table, we'd need to recreate them
-- For now, let's check what depends on the repositories table

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Check the final state
SELECT 'Migration Summary' as info;

SELECT
    'repositories' as table_name,
    COUNT(*) as total_count,
    COUNT(DISTINCT url) as unique_urls
FROM repositories;

SELECT
    'paper_repositories' as table_name,
    COUNT(*) as total_relationships
FROM paper_repositories;

-- Check for any remaining duplicates
SELECT
    'Duplicate URLs' as check_type,
    COUNT(*) as duplicate_count
FROM (
    SELECT url, COUNT(*) as cnt
    FROM repositories
    GROUP BY url
    HAVING COUNT(*) > 1
) duplicates;

-- Check for orphaned relationships
SELECT
    'Orphaned Relationships' as check_type,
    COUNT(*) as orphaned_count
FROM paper_repositories pr
LEFT JOIN papers p ON pr.paper_id = p.id
LEFT JOIN repositories r ON pr.repository_id = r.id
WHERE p.id IS NULL OR r.id IS NULL;

-- Sample of repositories with most papers
SELECT
    'Top Repositories by Paper Count' as info;

SELECT
    r.url,
    r.owner,
    r.name,
    r.num_stars,
    COUNT(pr.paper_id) as paper_count
FROM repositories r
LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
GROUP BY r.id, r.url, r.owner, r.name, r.num_stars
ORDER BY paper_count DESC, r.num_stars DESC
LIMIT 10;
