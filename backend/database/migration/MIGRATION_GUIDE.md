# Repositories Many-to-Many Migration Guide

## Overview

This migration optimizes the repository storage by moving from a denormalized structure (where repository data was duplicated for each paper) to a proper many-to-many relationship with normalized repository storage.

## Changes Made

### 1. Database Schema Changes

#### Before (Inefficient):
```sql
-- Old structure: Repository data duplicated for each paper
CREATE TABLE repositories (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id),  -- Direct foreign key
    url VARCHAR(500),
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER,
    is_official BOOLEAN,
    source VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### After (Optimized):
```sql
-- New structure: Normalized repositories + junction table
CREATE TABLE repositories (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) UNIQUE,  -- No more paper_id, URL is unique
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER,
    is_official BOOLEAN,
    source VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE paper_repositories (
    paper_id BIGINT REFERENCES papers(id),
    repository_id BIGINT REFERENCES repositories(id),
    is_official BOOLEAN,  -- Per-paper official status
    source VARCHAR(50),   -- Source of this relationship
    created_at TIMESTAMP,
    PRIMARY KEY (paper_id, repository_id)
);
```

### 2. SQLAlchemy Model Changes

#### Repository Model:
- Removed `paper_id` field
- Added `unique=True` constraint on `url`
- Changed relationship to many-to-many via `paper_repositories`

#### New PaperRepository Model:
- Junction table model for many-to-many relationship
- Includes relationship metadata (`is_official`, `source`)

#### Paper Model:
- Updated relationship to use `secondary="paper_repositories"`

### 3. API Model Changes

#### Repository API Model:
- Removed `paper_id` field (repositories are now paper-agnostic)
- Updated documentation to reflect normalized structure

#### New PaperRepository API Model:
- Represents the relationship between papers and repositories
- Includes relationship metadata
- Optional embedded repository data for convenience

## Benefits

### 1. Storage Efficiency
- **Eliminates Duplication**: Popular repositories (like PyTorch, TensorFlow) were stored hundreds of times
- **Reduced Storage**: Significant reduction in database size
- **Consistent Data**: Single source of truth for repository metadata

### 2. Data Integrity
- **Unique URLs**: Prevents duplicate repositories with slight URL variations
- **Consistent Metadata**: Star counts and other metadata updated in one place
- **Referential Integrity**: Proper foreign key constraints

### 3. Query Performance
- **Better Indexing**: Indexes on normalized data are more efficient
- **Faster Aggregations**: Counting papers per repository is now efficient
- **Reduced Joins**: Many queries can work directly with repositories table

### 4. Maintenance Benefits
- **Easier Updates**: Repository metadata (stars, etc.) updated once
- **Cleaner Codebase**: Clear separation between repositories and relationships
- **Better Analytics**: Easy to analyze repository popularity across papers

## Migration Process

### 1. Run Migration Script
```bash
# Execute the migration SQL script on paperswithcode_hf database
PGPASSWORD=paperswithcode123 psql -U paperswithcode_user -d paperswithcode_hf -h localhost -f backend/database/migration/optimize_repositories_many_to_many.sql
```

### 2. Verify Migration
```bash
# Run verification script
uv run backend/database/migration/test_repositories_migration.py
```

### 3. Update Application Code
The following files need updates to work with the new structure:

#### Critical Updates Required:
- `backend/services/repository_service.py` - Update queries and logic
- `backend/routers/repositories.py` - Update API endpoints
- Any scripts that insert/update repository data

#### Files That May Need Updates:
- `cron/daily/import_hf_daily_papers.py`
- `backend/database/repos_and_pages_setup/batch_extract.py`
- `backend/database/repos_and_pages_setup/populate_repos_and_pages_from_hf.py`
- `backend/database/repos_and_pages_setup/populate_official_repos.py`

## Code Update Patterns

### 1. Querying Repositories for a Paper

#### Before:
```python
repositories = session.query(Repository).filter(Repository.paper_id == paper_id).all()
```

#### After:
```python
# Option 1: Through relationship
paper = session.query(Paper).filter(Paper.id == paper_id).first()
repositories = paper.repositories

# Option 2: Through junction table
repositories = (
    session.query(Repository)
    .join(PaperRepository)
    .filter(PaperRepository.paper_id == paper_id)
    .all()
)
```

### 2. Adding a Repository to a Paper

#### Before:
```python
repo = Repository(
    paper_id=paper_id,
    url=url,
    owner=owner,
    name=name,
    num_stars=stars
)
session.add(repo)
```

#### After:
```python
# First, get or create the repository
repo = session.query(Repository).filter(Repository.url == url).first()
if not repo:
    repo = Repository(url=url, owner=owner, name=name, num_stars=stars)
    session.add(repo)
    session.flush()  # Get the ID

# Then create the relationship
paper_repo = PaperRepository(
    paper_id=paper_id,
    repository_id=repo.id,
    is_official=is_official,
    source=source
)
session.add(paper_repo)
```

### 3. Updating Repository Stars

#### Before:
```python
# Had to update multiple records
session.query(Repository).filter(Repository.url == url).update({
    Repository.num_stars: new_stars
})
```

#### After:
```python
# Update once for all papers
repo = session.query(Repository).filter(Repository.url == url).first()
if repo:
    repo.num_stars = new_stars
```

## API Changes

### 1. Repository Endpoints

#### GET /api/v1/repositories/
- Now returns normalized repositories (without paper_id)
- Each repository can be associated with multiple papers
- Added paper_count field showing how many papers use this repository

#### GET /api/v1/papers/{paper_id}/repositories
- Returns repositories associated with a specific paper
- Includes relationship metadata (is_official, source)
- Can include full repository details or just IDs

### 2. New Endpoints

#### GET /api/v1/repositories/{repo_id}/papers
- Get all papers that use a specific repository
- Useful for finding related work

#### POST /api/v1/papers/{paper_id}/repositories
- Associate a repository with a paper
- Handles creation of new repositories if needed

## Rollback Plan

If issues are discovered, the migration can be rolled back:

```sql
-- Rollback steps (if needed)
DROP TABLE repositories CASCADE;
DROP TABLE paper_repositories CASCADE;
ALTER TABLE repositories_backup RENAME TO repositories;
-- Recreate original indexes and constraints
```

The original data is preserved in `repositories_backup` table until the migration is confirmed successful.

## Testing Checklist

- [ ] Migration script runs without errors
- [ ] All original repository data is preserved
- [ ] No duplicate URLs in new repositories table
- [ ] All paper-repository relationships are maintained
- [ ] Indexes and constraints are properly created
- [ ] API endpoints return expected data
- [ ] Repository star updates work correctly
- [ ] Paper repository associations work correctly

## Performance Expectations

### Storage Reduction
- Expected 60-80% reduction in repository table size
- Faster queries on repository metadata
- More efficient star count updates

### Query Performance
- Repository listing: 2-3x faster
- Paper repository lookup: Similar performance
- Repository star updates: 10-100x faster (depending on popularity)

## Monitoring

After migration, monitor:
- Query performance on repository endpoints
- Database size reduction
- Any application errors related to repository operations
- Star count update job performance
