-- Restore and Deduplicate Repositories
-- This script properly restores the repositories from backup while deduplicating
-- Database: paperswithcode_hf

-- =============================================================================
-- STEP 1: Analyze the backup data
-- =============================================================================

SELECT 'BACKUP DATA ANALYSIS' as info;

SELECT
    COUNT(*) as total_backup_repos,
    COUNT(DISTINCT url) as unique_urls,
    COUNT(DISTINCT CONCAT(COALESCE(owner, ''), '/', COALESCE(name, ''))) as unique_owner_name_pairs,
    COUNT(*) - COUNT(DISTINCT url) as url_duplicates
FROM repositories_backup
WHERE url IS NOT NULL AND url != '';

-- Show top duplicates by owner/name
SELECT
    'TOP DUPLICATES BY OWNER/NAME' as info;

SELECT
    owner,
    name,
    COUNT(*) as duplicate_count
FROM repositories_backup
WHERE owner IS NOT NULL AND name IS NOT NULL
GROUP BY owner, name
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC
LIMIT 10;

-- =============================================================================
-- STEP 2: Insert deduplicated repositories
-- =============================================================================

-- Insert repositories deduplicated by URL (primary deduplication)
INSERT INTO repositories (url, owner, name, num_stars, is_official, source, created_at, updated_at, num_stars_updated_at)
SELECT DISTINCT ON (url)
    url,
    owner,
    name,
    num_stars,
    is_official,
    COALESCE(source, 'unknown') as source,
    created_at,
    updated_at,
    num_stars_updated_at
FROM repositories_backup
WHERE url IS NOT NULL AND url != ''
ORDER BY url, num_stars DESC NULLS LAST, updated_at DESC NULLS LAST;

-- =============================================================================
-- STEP 3: Rebuild paper_repositories relationships
-- =============================================================================

-- Create relationships using URL matching (since URLs are now unique)
INSERT INTO paper_repositories (paper_id, repository_id)
SELECT DISTINCT
    rb.paper_id,
    r.id as repository_id
FROM repositories_backup rb
JOIN repositories r ON rb.url = r.url
WHERE rb.paper_id IS NOT NULL
ON CONFLICT (paper_id, repository_id) DO NOTHING;

-- =============================================================================
-- STEP 4: Verification
-- =============================================================================

SELECT 'RESTORATION COMPLETE - VERIFICATION' as info;

-- Check repositories table
SELECT
    'repositories' as table_name,
    COUNT(*) as total_count,
    COUNT(DISTINCT url) as unique_urls,
    COUNT(DISTINCT CONCAT(COALESCE(owner, ''), '/', COALESCE(name, ''))) as unique_owner_name_pairs
FROM repositories;

-- Check paper_repositories table
SELECT
    'paper_repositories' as table_name,
    COUNT(*) as total_relationships,
    COUNT(DISTINCT paper_id) as unique_papers,
    COUNT(DISTINCT repository_id) as unique_repositories
FROM paper_repositories;

-- Verify no URL duplicates
SELECT
    'URL DUPLICATES CHECK' as check_type,
    COUNT(*) as duplicate_urls
FROM (
    SELECT url, COUNT(*) as cnt
    FROM repositories
    GROUP BY url
    HAVING COUNT(*) > 1
) duplicates;

-- Show sample of restored repositories
SELECT
    'SAMPLE RESTORED REPOSITORIES' as info;

SELECT
    r.owner || '/' || r.name as repository,
    r.num_stars,
    COUNT(pr.paper_id) as paper_count
FROM repositories r
LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
WHERE r.owner IS NOT NULL AND r.name IS NOT NULL
GROUP BY r.id, r.owner, r.name, r.num_stars
ORDER BY paper_count DESC, r.num_stars DESC
LIMIT 10;

-- Show repositories that were previously duplicated (now deduplicated)
SELECT
    'PREVIOUSLY DUPLICATED (NOW UNIQUE)' as info;

SELECT
    r.owner || '/' || r.name as repository,
    r.num_stars,
    COUNT(pr.paper_id) as paper_count,
    (
        SELECT COUNT(*)
        FROM repositories_backup rb
        WHERE rb.owner = r.owner AND rb.name = r.name
    ) as was_duplicated_count
FROM repositories r
LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
WHERE r.owner IS NOT NULL AND r.name IS NOT NULL
  AND (
      SELECT COUNT(*)
      FROM repositories_backup rb
      WHERE rb.owner = r.owner AND rb.name = r.name
  ) > 1
GROUP BY r.id, r.owner, r.name, r.num_stars
ORDER BY was_duplicated_count DESC, paper_count DESC
LIMIT 10;
