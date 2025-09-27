-- Final repositories migration - to be run as postgres user
-- This script completes the migration by replacing the original table

-- =============================================================================
-- STEP 1: Verify the new structure is ready
-- =============================================================================

-- Check that repositories_new has deduplicated data
SELECT 'Checking repositories_new deduplication' as status;
SELECT
    COUNT(*) as total_repos,
    COUNT(DISTINCT url) as unique_urls,
    COUNT(*) - COUNT(DISTINCT url) as duplicates
FROM repositories_new;

-- Check that paper_repositories has valid relationships
SELECT 'Checking paper_repositories relationships' as status;
SELECT COUNT(*) as total_relationships FROM paper_repositories;

-- Check for orphaned relationships
SELECT 'Checking for orphaned relationships' as status;
SELECT COUNT(*) as orphaned_count
FROM paper_repositories pr
LEFT JOIN papers p ON pr.paper_id = p.id
LEFT JOIN repositories_new r ON pr.repository_id = r.id
WHERE p.id IS NULL OR r.id IS NULL;

-- =============================================================================
-- STEP 2: Replace the original repositories table
-- =============================================================================

-- Begin transaction for atomic replacement
BEGIN;

-- Drop the original repositories table (this will cascade to any dependent objects)
DROP TABLE IF EXISTS repositories CASCADE;

-- Rename repositories_new to repositories
ALTER TABLE repositories_new RENAME TO repositories;

-- Rename the sequence
ALTER SEQUENCE repositories_new_id_seq RENAME TO repositories_id_seq;

-- Recreate any indexes that might have been dropped
CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);
CREATE INDEX IF NOT EXISTS idx_repositories_owner ON repositories(owner);
CREATE INDEX IF NOT EXISTS idx_repositories_name ON repositories(name);
CREATE INDEX IF NOT EXISTS idx_repositories_stars ON repositories(num_stars DESC);
CREATE INDEX IF NOT EXISTS idx_repositories_source ON repositories(source);
CREATE INDEX IF NOT EXISTS idx_repositories_created_at ON repositories(created_at);
CREATE INDEX IF NOT EXISTS idx_repositories_updated_at ON repositories(updated_at);

-- Make sure the URL is unique
CREATE UNIQUE INDEX IF NOT EXISTS idx_repositories_url_unique ON repositories(url);

-- Commit the transaction
COMMIT;

-- =============================================================================
-- STEP 3: Grant proper permissions
-- =============================================================================

-- Grant permissions to paperswithcode_user
GRANT ALL PRIVILEGES ON TABLE repositories TO paperswithcode_user;
GRANT ALL PRIVILEGES ON TABLE paper_repositories TO paperswithcode_user;
GRANT USAGE, SELECT ON SEQUENCE repositories_id_seq TO paperswithcode_user;

-- =============================================================================
-- STEP 4: Final verification
-- =============================================================================

SELECT 'Final Migration Status' as info;

-- Check final repository count
SELECT
    'repositories' as table_name,
    COUNT(*) as total_count,
    COUNT(DISTINCT url) as unique_urls
FROM repositories;

-- Check relationships
SELECT
    'paper_repositories' as table_name,
    COUNT(*) as total_relationships
FROM paper_repositories;

-- Check for duplicates (should be 0)
SELECT
    'Duplicate URLs' as check_type,
    COUNT(*) as duplicate_count
FROM (
    SELECT url, COUNT(*) as cnt
    FROM repositories
    GROUP BY url
    HAVING COUNT(*) > 1
) duplicates;

-- Check for orphaned relationships (should be 0)
SELECT
    'Orphaned Relationships' as check_type,
    COUNT(*) as orphaned_count
FROM paper_repositories pr
LEFT JOIN papers p ON pr.paper_id = p.id
LEFT JOIN repositories r ON pr.repository_id = r.id
WHERE p.id IS NULL OR r.id IS NULL;

-- Show top repositories by paper count
SELECT
    'Top 5 Repositories by Paper Count' as info;

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
LIMIT 5;
