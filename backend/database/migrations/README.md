# Database Migrations

This directory contains database migration scripts for the PapersWithCode backend.

## Running Migrations

To run a migration, use the `psql` command:

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_keywords_to_methods.sql
```

Or using environment variables:

```bash
psql -h localhost -U postgres -d paperswithcode_hf < backend/database/migrations/add_keywords_to_methods.sql
```

## Available Migrations

### Add Keywords to Methods (2025-10-13)

**Forward Migration:** `add_keywords_to_methods.sql`
- Adds a `keywords` TEXT column to the `methods` table
- Creates a full-text search index on the keywords column
- Allows storing comma-separated keywords for method matching

**Rollback Migration:** `rollback_keywords_from_methods.sql`
- Removes the `keywords` column from the `methods` table
- Drops the associated index

**Usage Example:**
```bash
# Apply the migration
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_keywords_to_methods.sql

# Rollback if needed
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/rollback_keywords_from_methods.sql
```

## Notes

- The `tasks` table already has a `keywords` column, so no migration is needed for tasks
- Migrations use `IF NOT EXISTS` / `IF EXISTS` clauses to be idempotent
- Always test migrations on a development database first
- Create backups before running migrations on production
