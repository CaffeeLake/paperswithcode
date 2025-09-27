-- Migration Script: Optimize Repositories Table for Many-to-Many Relationship
-- Database: paperswithcode_hf
-- This script restructures the repositories table to eliminate duplicate repository data
-- and creates a proper many-to-many relationship between papers and repositories

-- =============================================================================
-- STEP 1: BACKUP EXISTING DATA
-- =============================================================================

-- Create a backup of the current repositories table
CREATE TABLE IF NOT EXISTS repositories_backup AS
SELECT * FROM repositories;

-- =============================================================================
-- STEP 2: CREATE NEW OPTIMIZED REPOSITORIES TABLE
-- =============================================================================

-- Create the new repositories table without paper_id (normalized)
CREATE TABLE IF NOT EXISTS repositories_new (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) NOT NULL UNIQUE,  -- URL should be unique across all repositories
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- STEP 3: CREATE PAPER_REPOSITORIES JUNCTION TABLE
-- =============================================================================

-- Create the many-to-many junction table
CREATE TABLE IF NOT EXISTS paper_repositories (
    paper_id BIGINT NOT NULL,
    repository_id BIGINT NOT NULL,
    is_official BOOLEAN DEFAULT FALSE,  -- Whether this repo is official for this specific paper
    source VARCHAR(50) DEFAULT 'unknown',  -- Source of this paper-repo relationship
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Primary key is composite
    PRIMARY KEY (paper_id, repository_id),

    -- Foreign key constraints
    CONSTRAINT fk_paper_repositories_paper_id
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_repositories_repository_id
        FOREIGN KEY (repository_id) REFERENCES repositories_new(id) ON DELETE CASCADE
);

-- =============================================================================
-- STEP 4: MIGRATE DATA FROM OLD TO NEW STRUCTURE
-- =============================================================================

-- Insert unique repositories into the new table
-- This deduplicates repositories that were previously stored multiple times
INSERT INTO repositories_new (url, owner, name, num_stars, is_official, source, created_at, updated_at)
SELECT DISTINCT ON (url)
    url,
    owner,
    name,
    MAX(num_stars) as num_stars,  -- Take the highest star count if there are duplicates
    BOOL_OR(is_official) as is_official,  -- True if any instance was marked as official
    source,
    MIN(created_at) as created_at,  -- Take the earliest creation date
    MAX(updated_at) as updated_at   -- Take the latest update date
FROM repositories
WHERE url IS NOT NULL AND url != ''
GROUP BY url, owner, name, source
ORDER BY url, updated_at DESC;

-- Create the paper-repository relationships
-- This preserves all the many-to-many relationships from the original table
INSERT INTO paper_repositories (paper_id, repository_id, is_official, source, created_at)
SELECT DISTINCT
    r_old.paper_id,
    r_new.id as repository_id,
    r_old.is_official,
    r_old.source,
    r_old.created_at
FROM repositories r_old
JOIN repositories_new r_new ON r_old.url = r_new.url
WHERE r_old.paper_id IS NOT NULL;

-- =============================================================================
-- STEP 5: CREATE INDEXES FOR PERFORMANCE
-- =============================================================================

-- Indexes for the new repositories table
CREATE INDEX IF NOT EXISTS idx_repositories_new_url ON repositories_new(url);
CREATE INDEX IF NOT EXISTS idx_repositories_new_owner ON repositories_new(owner);
CREATE INDEX IF NOT EXISTS idx_repositories_new_name ON repositories_new(name);
CREATE INDEX IF NOT EXISTS idx_repositories_new_stars ON repositories_new(num_stars DESC);
CREATE INDEX IF NOT EXISTS idx_repositories_new_source ON repositories_new(source);
CREATE INDEX IF NOT EXISTS idx_repositories_new_created_at ON repositories_new(created_at);
CREATE INDEX IF NOT EXISTS idx_repositories_new_updated_at ON repositories_new(updated_at);

-- Indexes for the junction table
CREATE INDEX IF NOT EXISTS idx_paper_repositories_paper_id ON paper_repositories(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_repositories_repository_id ON paper_repositories(repository_id);
CREATE INDEX IF NOT EXISTS idx_paper_repositories_official ON paper_repositories(is_official);
CREATE INDEX IF NOT EXISTS idx_paper_repositories_source ON paper_repositories(source);

-- =============================================================================
-- STEP 6: REPLACE OLD TABLE WITH NEW TABLE
-- =============================================================================

-- Drop the old repositories table and rename the new one
-- Note: This should be done in a transaction in production
BEGIN;

-- Drop the old table (this will also drop its indexes and constraints)
DROP TABLE IF EXISTS repositories CASCADE;

-- Rename the new table to the original name
ALTER TABLE repositories_new RENAME TO repositories;

-- Update any sequences to match the new table name
ALTER SEQUENCE IF EXISTS repositories_new_id_seq RENAME TO repositories_id_seq;

COMMIT;

-- =============================================================================
-- STEP 7: VERIFICATION QUERIES
-- =============================================================================

-- These queries can be used to verify the migration was successful

-- Check repository count before and after
-- SELECT 'Original count' as label, COUNT(*) as count FROM repositories_backup
-- UNION ALL
-- SELECT 'New unique count' as label, COUNT(*) as count FROM repositories
-- UNION ALL
-- SELECT 'Relationships count' as label, COUNT(*) as count FROM paper_repositories;

-- Check for any orphaned relationships
-- SELECT COUNT(*) as orphaned_relationships
-- FROM paper_repositories pr
-- LEFT JOIN papers p ON pr.paper_id = p.id
-- LEFT JOIN repositories r ON pr.repository_id = r.id
-- WHERE p.id IS NULL OR r.id IS NULL;

-- Check duplicate URLs (should be 0)
-- SELECT url, COUNT(*) as duplicate_count
-- FROM repositories
-- GROUP BY url
-- HAVING COUNT(*) > 1;

-- Sample data comparison
-- SELECT 'Sample repositories with papers' as info;
-- SELECT r.url, r.owner, r.name, r.num_stars, COUNT(pr.paper_id) as paper_count
-- FROM repositories r
-- LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
-- GROUP BY r.id, r.url, r.owner, r.name, r.num_stars
-- ORDER BY paper_count DESC, r.num_stars DESC
-- LIMIT 10;

-- =============================================================================
-- NOTES FOR ROLLBACK (if needed)
-- =============================================================================

-- If rollback is needed, the original data is preserved in repositories_backup
-- To rollback:
-- 1. DROP TABLE repositories CASCADE;
-- 2. DROP TABLE paper_repositories CASCADE;
-- 3. ALTER TABLE repositories_backup RENAME TO repositories;
-- 4. Recreate original indexes and constraints

-- =============================================================================
-- CLEANUP (run after verification)
-- =============================================================================

-- After verifying the migration is successful, you can drop the backup table:
-- DROP TABLE repositories_backup;
