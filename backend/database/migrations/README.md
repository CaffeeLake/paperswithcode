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

### Normalize Benchmark Source Papers (2026-05-09)

**Forward Migration:** `normalize_benchmark_source_papers.sql`
- Links active benchmark datasets to local `papers` rows when `paper_url` contains a resolvable arXiv ID
- Normalizes `introducing_paper_id`, `introducing_paper_title`, canonical arXiv `paper_url`, and missing `introduced_year`
- Idempotent and limited to datasets used by evaluations or task-dataset metrics

### Backfill Terminal Bench Source Paper (2026-05-09)

**Forward Migration:** `backfill_terminal_bench_source_paper.sql`
- Links the `terminal-bench` dataset to paper `2601.11868`
- Sets `datasets.introducing_paper_id`, `introducing_paper_title`, and `paper_url`
- Idempotent: only updates the `terminal-bench` slug and falls back gracefully if any field is already set

### Remove Duplicate ViT Method (2026-05-09)

**Forward Migration:** `remove_duplicate_vit_method.sql`
- Moves any `vit` paper associations to the canonical `vision-transformer` method
- Deletes the duplicate `vit` method row
- Prints transferred association and deleted method counts

### Add Method Source Paper Links (2026-05-09)

**Forward Migration:** `add_method_source_paper_id.sql`
- Adds nullable `methods.source_paper_id` referencing `papers(id)`
- Backfills local `methods.source_url` paper routes into explicit source paper links
- Inserts missing `paper_methods` rows for canonical source links
- Prints a migration report with backfilled, already linked, non-local, and unresolved counts

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
