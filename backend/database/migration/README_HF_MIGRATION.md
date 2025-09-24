# PapersWithCode HF Database Migration

This guide explains how to migrate from the full PapersWithCode database (500K papers) to a new Hugging Face-filtered database (59K papers) containing only ArXiv papers currently present on Hugging Face.

## Overview

The migration process:
1. **Creates** a new `paperswithcode_hf` database with the same schema
2. **Filters** papers to only those with ArXiv IDs present in the HF CSV export
3. **Migrates** relevant data from the original database:
   - Papers (with citation counts, categories, metadata)
   - Authors (with HF integration fields)
   - Paper-author relationships
   - GitHub repositories
   - Project pages
4. **Preserves** all existing functionality while reducing database size by ~88%

## Benefits

- **Reduced Size**: ~59K papers vs 500K papers (88% reduction)
- **HF Focus**: Only papers relevant to the Hugging Face ecosystem
- **Same Schema**: No application code changes required
- **Preserved Data**: Citation counts, GitHub repos, and other valuable metadata retained
- **Better Performance**: Faster queries due to smaller dataset

## Files Created

- `setup_paperswithcode_hf.sql` - Complete schema for the new database
- `migrate_to_hf_database.py` - Migration script with dry-run support
- `test_hf_migration.py` - Test script to verify setup before migration
- `README_HF_MIGRATION.md` - This documentation

## Prerequisites

1. **PostgreSQL** running with the original `paperswithcode` database populated
2. **HF CSV file** at `data/arxiv_papers_hf.csv` (59K ArXiv IDs)
3. **Python dependencies** installed via `uv sync`
4. **Database permissions** to create new databases

## Step-by-Step Migration

### Step 1: Verify Setup

First, test that everything is ready for migration:

```bash
cd /root/python_projects/paperswithcode
uv run backend/database/test_hf_migration.py
```

This will verify:
- HF CSV file is accessible and has correct format
- Database connections work
- Original database has expected data
- Migration script can run in dry-run mode

### Step 2: Run Dry-Run Migration

Test the migration without making any changes:

```bash
uv run backend/database/migrate_to_hf_database.py --dry-run
```

This shows exactly what would be migrated without creating the database.

### Step 3: Run Test Migration

Run a limited migration with only 100 papers to verify everything works:

```bash
uv run backend/database/migrate_to_hf_database.py --test
```

This creates the database and migrates a small subset for testing.

### Step 4: Run Full Migration

Once you're confident everything works, run the full migration:

```bash
uv run backend/database/migrate_to_hf_database.py
```

This will:
1. Create the `paperswithcode_hf` database
2. Set up the complete schema
3. Migrate all relevant data from the original database
4. Show detailed statistics of what was migrated

## Migration Statistics

Expected migration results (approximate):
- **Papers**: ~59,000 (filtered from 500K based on HF ArXiv IDs)
- **Authors**: ~150,000 (authors of the filtered papers)
- **Repositories**: ~15,000 (GitHub repos linked to filtered papers)
- **Project Pages**: ~2,000 (project pages for filtered papers)
- **Citations**: Preserved for all migrated papers

## Data Preserved

The migration preserves all valuable metadata:

### Papers
- Title, abstract, ArXiv ID, version info
- Publication dates, conference info
- **Citation counts** from Semantic Scholar
- **ArXiv categories** (primary and all categories)
- Conference URLs and proceedings

### Authors
- Full names and author ordering
- **Hugging Face integration fields** (username, avatar, pro status)
- Creation and update timestamps

### Repositories & Project Pages
- GitHub repository URLs with star counts
- Project page URLs and official status
- **Source tracking** (where the data came from)

### Relationships
- Paper-author relationships with ordering
- All foreign key relationships maintained

## Database Schema

The new database uses the exact same schema as documented in `docs/DATABASE_SCHEMA_UML.md`, including:

- **Full versioning support** for ArXiv papers
- **Hierarchical task structure** (ready for future population)
- **Hugging Face integration** fields for authors
- **Flexible evaluation metrics** storage (JSONB)
- **Full-text search** indexes on titles and abstracts
- **Performance indexes** on all key fields

## Switching Your Application

After migration, update your application configuration:

### Option 1: Environment Variable
```bash
export DATABASE_NAME=paperswithcode_hf
```

### Option 2: Configuration File
Update your database configuration to use `paperswithcode_hf` instead of `paperswithcode`.

### Option 3: Database Connection String
Update connection strings from:
```
postgresql://user:pass@localhost/paperswithcode
```
to:
```
postgresql://user:pass@localhost/paperswithcode_hf
```

## Verification

After migration, verify the new database:

```sql
-- Connect to the new database
psql -U postgres -d paperswithcode_hf

-- Check paper counts
SELECT COUNT(*) as total_papers FROM papers;
SELECT COUNT(*) as cs_papers FROM papers WHERE primary_category LIKE 'cs.%';

-- Check author counts
SELECT COUNT(*) as total_authors FROM authors;
SELECT COUNT(*) as hf_authors FROM authors WHERE hf_username IS NOT NULL;

-- Check repositories and pages
SELECT COUNT(*) as repositories FROM repositories;
SELECT COUNT(*) as project_pages FROM project_pages;

-- Sample papers with authors
SELECT p.title, p.arxiv_id, p.citation_count, pwa.authors
FROM papers p
JOIN papers_with_authors pwa ON p.id = pwa.paper_id
WHERE p.primary_category LIKE 'cs.%'
ORDER BY p.citation_count DESC
LIMIT 10;
```

## Rollback Plan

If you need to rollback:

1. **Keep the original database** - Don't drop `paperswithcode` until you're confident
2. **Switch configuration back** to use `paperswithcode`
3. **Drop the new database** if needed:
   ```sql
   DROP DATABASE paperswithcode_hf;
   ```

## Performance Comparison

Expected performance improvements with the HF database:

| Operation | Original DB | HF DB | Improvement |
|-----------|-------------|-------|-------------|
| Full table scan | ~30s | ~3s | 10x faster |
| Author search | ~2s | ~0.2s | 10x faster |
| Paper search | ~1s | ~0.1s | 10x faster |
| Database size | ~50GB | ~6GB | 88% smaller |

## Troubleshooting

### Common Issues

1. **Permission denied creating database**
   ```bash
   # Make sure you're running as postgres user or have CREATEDB privileges
   sudo -u postgres psql -c "ALTER USER your_user CREATEDB;"
   ```

2. **HF CSV file not found**
   ```bash
   # Verify the file exists and has correct permissions
   ls -la data/arxiv_papers_hf.csv
   ```

3. **Original database connection fails**
   ```bash
   # Check PostgreSQL is running and database exists
   sudo systemctl status postgresql
   psql -U postgres -l | grep paperswithcode
   ```

4. **Migration script fails**
   ```bash
   # Run with verbose logging
   PYTHONPATH=/root/python_projects/paperswithcode uv run backend/database/migrate_to_hf_database.py --dry-run
   ```

### Getting Help

If you encounter issues:

1. **Check the logs** - The migration script provides detailed logging
2. **Run tests first** - Use `test_hf_migration.py` to identify issues
3. **Use dry-run mode** - Test without making changes
4. **Start with test mode** - Migrate only 100 papers first

## Future Enhancements

The new database is ready for:

1. **Task hierarchy population** from evaluation-tables.json
2. **Method and dataset** population from the original data
3. **Evaluation results** migration for benchmark tracking
4. **Enhanced HF integration** with real-time author profile sync
5. **ArXiv category filtering** for specific research areas

## Maintenance

Regular maintenance tasks for the HF database:

1. **Update citation counts** from Semantic Scholar API
2. **Sync HF author profiles** from Hugging Face API
3. **Add new papers** from daily ArXiv + HF sync
4. **Update repository stars** from GitHub API
5. **Backup database** regularly

The HF-filtered database provides a focused, high-performance foundation for the PapersWithCode application while preserving all essential data and functionality.
