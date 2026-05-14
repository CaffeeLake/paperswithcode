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

### Make Retrieval a Subtask of Embedding Models (2026-05-14)

**Forward Migration:** `make_retrieval_embedding_subtask.sql`
- Sets `retrieval.parent_id` to the `embedding-models` task id and
  `retrieval.level = embedding-models.level + 1`
- Clears `retrieval.area_id` so it no longer appears as a top-level card on
  `/tasks` (matches the `language-modeling` subtask model)
- Idempotent: a `DO $$ ... $$` block resolves both rows by slug and the UPDATE
  is a no-op once `retrieval` is already reparented

```bash
psql -U postgres -d paperswithcode_hf \
     -f backend/database/migrations/make_retrieval_embedding_subtask.sql
```

### Reorganize Task Areas by Modality (2026-05-13)

**Forward Migration:** `reorganize_task_areas.sql`
- Renames area `Computer Vision` -> `Vision` (description rewritten to focus on still images)
- Renames area `Natural Language Processing` -> `Language`
- Creates a new `Video` area
- Moves `video-classification`, `video-generation`, `video-segmentation` from Vision -> Video
- Moves `ocr` from Vision -> General
- Moves `image-understanding` from General -> Vision and `video-understanding` from General -> Video
- Resyncs the `areas_id_seq` sequence with `MAX(id)` before inserting Video so the autoincrement does not collide with pre-existing gap IDs
- Idempotent: name updates are no-ops if already renamed; the Video insert is guarded by `NOT EXISTS`; the task moves use slug filters

```bash
psql -U postgres -d paperswithcode_hf \
     -f backend/database/migrations/reorganize_task_areas.sql
```

### Add Language Modeling Subtasks (2026-05-13)

**Forward Migration:** `add_language_modeling_subtasks.sql`
- Creates 8 child tasks under `language-modeling` with their own descriptions
  (`world-knowledge`, `long-context`, `instruction-following`, `math`,
  `language-reasoning`, `coding`, `safety-and-grounding`,
  `classic-language-modeling`)
- Moves all `task_datasets`, `task_dataset_metrics`, and `evaluations` rows
  from the parent `language-modeling` task to the appropriate child subtask
  for each benchmark
- Idempotent: uses `ON CONFLICT` and only rewrites rows still on the parent

**Wrapper:** `run_add_language_modeling_subtasks.py`
- Applies the SQL migration above and then recalculates `evaluations.best_rank`
  per `(child_task_id, dataset_id, best_metric)` triple via
  `EvaluationService.recalculate_ranks`

```bash
uv run --env-file backend/keys.env python \
    backend/database/migrations/run_add_language_modeling_subtasks.py
```

### Add Evaluation Harness Column (2026-05-12)

**Forward Migration:** `add_evaluations_harness.sql`
- Adds nullable `evaluations.harness` (VARCHAR(255)) for model+harness benchmarks like Terminal-Bench
- Backfills existing Terminal-Bench rows by splitting harness names out of `model_name`:
  - `GLM-5.1 (best self-reported, Claude Code)` -> `GLM-5.1` + harness `Claude Code`
  - `GLM-5.1 (Terminus-2)` -> `GLM-5.1` + harness `Terminus-2`
  - `GLM-4.5 (355B)` -> `GLM-4.5` + harness `Terminus`
  - `DeepSeek-V4-*` -> harness `unknown`
- Idempotent: column add uses `IF NOT EXISTS`, backfills are scoped to the `terminal-bench` slug and match the original model names so re-running is a no-op

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
