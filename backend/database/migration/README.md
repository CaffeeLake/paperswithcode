# Database Migration Scripts

This directory contains the essential migration scripts for the PapersWithCode database. The database has been normalized to use many-to-many relationships for repositories and project pages.

## Current Database Schema

The database uses a **normalized schema** with the following key characteristics:

### Repositories
- **`repositories`** table: Stores unique repositories with `num_stars`, `is_official`, etc.
- **`paper_repositories`** table: Junction table with only `paper_id` and `repository_id`
- No direct `paper_id` foreign key in the repositories table

### Project Pages
- **`project_pages`** table: Stores unique project pages normalized without direct paper reference
- **`paper_project_pages`** table: Junction table for many-to-many relationship

## Essential Files

### 1. Database Setup
- **`setup_paperswithcode_hf.sql`** - Complete database schema setup script
  - Creates all tables with normalized many-to-many relationships
  - Includes proper indexes and constraints
  - Updated to match current schema in `docs/DATABASE_SCHEMA_UML.md`

### 2. Data Migration Scripts
- **`migrate_citations.py`** - Migrate citation counts and Semantic Scholar IDs
- **`populate_hf_database.py`** - Direct data migration from original database
- **`migrate_to_hf_database_simple.py`** - Simplified migration with dry-run support
- **`migrate_to_hf_database.py`** - Full migration script with comprehensive options

### 3. Testing & Documentation
- **`test_hf_migration.py`** - Test script for migration validation
- **`README_HF_MIGRATION.md`** - Detailed migration documentation

## Usage

### 1. Fresh Database Setup
```bash
# Create the database schema
psql -U postgres -d paperswithcode_hf -f setup_paperswithcode_hf.sql
```

### 2. Data Migration
```bash
# Dry run to see what would be migrated
uv run backend/database/migration/migrate_to_hf_database_simple.py --dry-run

# Execute the migration
uv run backend/database/migration/migrate_to_hf_database_simple.py --execute

# Migrate citations (much faster than re-populating)
uv run backend/database/migration/migrate_citations.py --execute
```

### 3. Validation
```bash
# Test the migration results
uv run backend/database/migration/test_hf_migration.py
```

## Schema Changes Made

### ✅ Normalized Structure
- **Repositories**: Removed `paper_id`, added `UNIQUE` constraint on `url`
- **Project Pages**: Removed direct paper reference, normalized structure
- **Junction Tables**: Added `paper_repositories` and `paper_project_pages`

### ✅ Performance Optimizations
- Unique URL constraints prevent duplicates
- Proper indexes for many-to-many relationships
- Optimized for CRON job efficiency (star count updates)

### ✅ Data Integrity
- Foreign key constraints on junction tables
- Referential integrity maintained
- No data loss during normalization

## Query Examples

### Get repositories for paper ID 289:
```sql
SELECT r.*
FROM repositories r
JOIN paper_repositories pr ON r.id = pr.repository_id
WHERE pr.paper_id = 289
ORDER BY r.num_stars DESC;
```

### Get project pages for a paper:
```sql
SELECT pp.*
FROM project_pages pp
JOIN paper_project_pages ppp ON pp.id = ppp.project_page_id
WHERE ppp.paper_id = 289;
```

## Migration Status

✅ **Database schema normalized and updated**
✅ **Outdated migration scripts removed**
✅ **Essential migration scripts preserved**
✅ **Documentation updated to reflect current state**

The migration folder is now clean and contains only the essential files needed for database setup and data migration.
