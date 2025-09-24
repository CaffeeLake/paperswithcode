# Repositories and Project Pages Setup

This directory contains scripts for setting up and managing the `repositories` and `project_pages` tables in the PapersWithCode database.

## Main Setup Script

### `setup_repositories_and_project_pages.sql`

This is the **consolidated script** that handles the complete setup process:

1. **Table Creation**: Creates `repositories` and `project_pages` tables with all necessary columns
2. **Schema Updates**: Adds `source` fields if they don't exist (for existing installations)
3. **Indexes**: Creates performance indexes for efficient querying
4. **Triggers**: Sets up `updated_at` triggers for automatic timestamp updates
5. **Duplicate Cleanup**: Removes duplicate entries and handles URL normalization
6. **Data Migration**: Updates legacy data sources to 'pwc_archive'
7. **Documentation**: Adds table and column comments
8. **Verification**: Shows statistics and verifies the setup

**Usage:**
```bash
# Run as regular database user
PGPASSWORD=paperswithcode123 psql -U paperswithcode_user -d paperswithcode_hf -h localhost -f setup_repositories_and_project_pages.sql

# Then run superuser operations (if needed)
sudo -u postgres psql -d paperswithcode_hf -f setup_repositories_and_project_pages_superuser.sql
```

### `setup_repositories_and_project_pages_superuser.sql`

Companion script for operations requiring superuser privileges:
- Adds unique constraints to prevent duplicate entries
- Should be run after the main setup script

## Features

### Duplicate Prevention
- **Unique Constraints**: `UNIQUE (paper_id, url)` on both tables
- **URL Normalization**: Handles URLs with/without trailing slashes
- **Idempotent Operations**: Can be run multiple times safely

### Data Sources Tracking
The `source` field tracks where data came from:
- `pwc_archive`: Original PapersWithCode data
- `ai_extraction`: AI-powered extraction from papers
- `hf_api`: Hugging Face API data
- `fast`: Fast extraction methods
- `manual`: Manually added entries

### Performance Optimizations
- Indexes on `paper_id`, `url`, `source`, and other frequently queried fields
- Optimized for search and filtering operations

## Table Schemas

### repositories
```sql
CREATE TABLE repositories (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (paper_id, url)
);
```

### project_pages
```sql
CREATE TABLE project_pages (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'unknown',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (paper_id, url)
);
```

## Historical Context

This consolidated script replaces the following individual scripts:
- `add_repositories_and_project_pages.sql` - Original table creation
- `add_source_fields.sql` - Added source tracking fields
- `fix_duplicate_project_pages.sql` - Fixed duplicate project pages issue
- `final_cleanup_and_constraint.sql` - URL normalization and constraints

### The Duplicate Issue (Resolved)
Previously, paper ID 52782 had 17 duplicate project pages due to:
1. Missing unique constraints allowing duplicate insertions
2. URL variations (with/without trailing slashes)
3. Multiple extraction processes running concurrently

The consolidated script prevents this by:
- Adding unique constraints upfront
- Normalizing URLs during cleanup
- Using idempotent operations that can handle existing data

## Verification

After running the setup, verify everything is working:

```sql
-- Check constraints are in place
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN ('repositories'::regclass, 'project_pages'::regclass)
AND contype = 'u';

-- Check for any remaining duplicates (should be 0)
SELECT paper_id, url, COUNT(*)
FROM project_pages
GROUP BY paper_id, url
HAVING COUNT(*) > 1;

-- Test duplicate prevention
INSERT INTO project_pages (paper_id, url, source)
VALUES (52782, 'https://3d.hunyuan.tencent.com', 'test');
-- Should fail with: duplicate key value violates unique constraint
```

## Future Usage

For new installations or updates:
1. Run the consolidated setup script
2. Run the superuser script if needed
3. The tables are ready for data population from extraction scripts

The extraction scripts (`batch_extract.py`, `fast_batch_extract.py`, etc.) will now properly handle duplicates due to the unique constraints.
