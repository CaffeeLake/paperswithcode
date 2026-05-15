# PapersWithCode - Database Schema & UML (Live, May 2026)

## Overview

This document reflects the live PostgreSQL schema of the PapersWithCode backend as of May 2026. It is derived directly from the database (schema-only dump and table descriptions) and should be treated as the source of truth for development.

Key capabilities:
- Leaderboards defined by triples: (task, dataset, metric)
- Rich dataset metadata and hierarchy (parent datasets, variants, licensing, modalities, languages)
- ArXiv versioning, citation tracking, and categories for papers
- Normalized repositories with trending scores and star history
- Normalized project pages with updatable API view
- Comprehensive indexing for search and filtering

## Entity Relationship Diagram (UML)

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────────────┐
│     AUTHORS     │    │      PAPERS      │    │           TASKS          │
├─────────────────┤    ├──────────────────┤    ├──────────────────────────┤
│ id (PK)         │    │ id (PK)          │    │ id (PK)                  │
│ name            │    │ title            │    │ name                     │
│ hf_username     │    │ abstract         │    │ description              │
│ hf_id           │    │ arxiv_id         │    │ slug (UNIQUE)            │
│ hf_avatar_url   │    │ version          │    │ parent_id (FK self)      │
│ hf_status       │    │ is_latest_version│    │ area_id (FK areas)       │
│ hf_is_pro       │    │ date_published   │    │ level (0=top-level,      │
│ created_at      │    │ proceeding       │    │   1=subtask,             │
│ updated_at      │    │ conference       │    │   2=sub-subtask, ...)    │
└─────────────────┘    │ citation_count   │    │ keywords, images         │
                       │ semantic_scholar │    │ created/updated          │
                       │ categories, flags│    └──────────────────────────┘
                       │ created_at/updated│             │
                       └──────────────────┘              │ (Self-referencing
                                │                        │  parent_id ─► tasks.id)
                                │                        ▼
                                │              ┌─────────────────┐
                                │              │      AREAS      │
                                │              ├─────────────────┤
                                │              │ id (PK)         │
                                │              │ name            │
                                │              │ description     │
                                │              │ created/updated │
                                │              └─────────────────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
       ▼                        ▼                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  PAPER_AUTHORS  │     │   PAPER_TASKS   │     │  PAPER_METHODS  │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ paper_id (FK)   │     │ paper_id (FK)   │     │ paper_id (FK)   │
│ author_id (FK)  │     │ task_id (FK)    │     │ method_id (FK)  │
│ author_order    │     │ PK (paper,task) │     │ PK (paper,method)│
│ PK (paper,author)│    └─────────────────┘     └─────────────────┘
└─────────────────┘
                                │
                                ▼
                         ┌───────────────┐
                         │    METHODS    │
                         ├───────────────┤
                         │ id (PK)       │
                         │ name          │
                         │ slug (UNIQUE) │
                         │ image fields  │
                         │ created/updated│
                         └───────────────┘

┌─────────────────┐     ┌─────────────────┐
│ PAPER_DATASETS  │     │   DATASETS      │
├─────────────────┤     ├─────────────────┤
│ paper_id (FK)   │     │ id (PK)         │
│ dataset_id (FK) │     │ name            │
│ PK (paper,ds)   │     │ slug (UNIQUE)   │
└─────────────────┘     │ rich metadata   │
                        │ parent_dataset  │
                        │ variants/splits │
                        │ licensing       │
                        │ modalities/lang │
                        │ created/updated │
                        └─────────────────┘
                                │
                                ▼
       ┌──────────────────────────────┐    ┌───────────────────────────────┐
       │       TASK_DATASETS          │    │     TASK_DATASET_METRICS      │
       ├──────────────────────────────┤    ├───────────────────────────────┤
       │ task_id (FK)                 │    │ task_id (FK)                  │
       │ dataset_id (FK)              │    │ dataset_id (FK)               │
       │ featured_rank (NULL or > 0)  │    │ metric_id (FK)                │
       │ supports_harness (bool)      │    │ PK (task,dataset,metric)      │
       │ PK (task, dataset)           │    │ (Defines leaderboards)        │
       │ (Display + harness metadata) │    └───────────────────────────────┘
       └──────────────────────────────┘
                                │
                                ▼
                        ┌──────────────────┐      ┌─────────────────┐
                        │   EVALUATIONS    │      │     METRICS     │
                        ├──────────────────┤      ├─────────────────┤
                        │ id (PK)          │      │ id (PK)         │
                        │ paper/task/ds FK │      │ name (UNIQUE)   │
                        │ metrics JSONB    │      │ direction (CHECK)│
                        │ best_metric (str)│      │ created/updated │
                        └──────────────────┘      └─────────────────┘
                        evaluations.task_id may reference any task in the
                        hierarchy (top-level OR child subtask). Leaderboards
                        are scoped to the most specific task.

┌─────────────────┐       ┌───────────────────────┐
│  REPOSITORIES   │       │  REPOSITORY_STAR_... │
├─────────────────┤       ├───────────────────────┤
│ id (PK)         │       │ id (PK)               │
│ url (UNIQUE)    │◄──────┤ repository_id (FK)    │
│ owner, name     │       │ num_stars, snapshot_at│
│ num_stars       │       │ UNIQUE(repo_id, time) │
│ trending_score  │       └───────────────────────┘
│ trending_at     │
│ created/updated │
└─────────────────┘
        │
        ▼
┌───────────────────────┐     ┌───────────────────────┐
│  PAPER_REPOSITORIES   │     │   PROJECT_PAGES       │
├───────────────────────┤     ├───────────────────────┤
│ paper_id (FK)         │     │ id (PK)               │
│ repository_id (FK)    │     │ url (UNIQUE indexed)  │
│ is_official           │     │ is_official, source   │
│ PK (paper,repo)       │     │ created/updated       │
└───────────────────────┘     └───────────────────────┘
        │                                      │
        ▼                                      ▼
┌────────────────────────┐            ┌────────────────────────┐
│  PAPER_PROJECT_PAGES   │            │  PROJECT_PAGES_API     │
├────────────────────────┤            ├────────────────────────┤
│ paper_id (FK)          │            │ updatable view over    │
│ project_page_id (FK)   │            │ project_pages (triggers│
│ PK (paper,project)     │            │ for insert/update/delete)
└────────────────────────┘            └────────────────────────┘

┌──────────────────────────┐
│      USER_BOOKMARKS      │
├──────────────────────────┤
│ hf_username (PK)         │
│ paper_id (FK papers, PK) │◄──── PAPERS.id (ON DELETE CASCADE)
│ created_at               │
│ PK (hf_username, paper_id)│
└──────────────────────────┘
```

## Core Tables (DDL highlights)

The following summarizes the live structure. See the database for full DDL.

### PAPERS
- id (PK), title, abstract
- arxiv_id, version, is_latest_version
- date_published, proceeding, conference, conference_url_abs, conference_url_pdf
- citation_count, semantic_scholar_id, citation_updated_at
- primary_category, all_categories[], urls_extracted
- tldr (TEXT, NULL — frontend v2 TL;DR panel; no generation pipeline yet)
- num_pages (INTEGER, NULL — source PDF page count; not surfaced in UI yet)
- created_at, updated_at
- Indexes: title/abstract full-text, arxiv_id, date, conference, latest flag, version, citation count, categories, urls_extracted (incl. partial cs.% index)

### AUTHORS
- id (PK), name (CHECK name not empty)
- hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro
- created_at, updated_at

### AREAS
- id (PK), name, description, created_at, updated_at

### TASKS
- id (PK), name, description, slug (UNIQUE)
- parent_id (FK self), area_id (FK), level (default 0)
- keywords, image_url, image_credit, useful_leaderboards
- created_at, updated_at
- Indexes: parent_id, area_id, slug
- **Hierarchy:** subtasks are child rows linked through `parent_id`. `level`
  is `0` for top-level tasks, `1` for subtasks under a top-level task,
  `2` for sub-subtasks, etc. Each subtask has its own page, description,
  benchmarks, and evaluations. Example: `language-modeling` (level 0) has
  child subtasks `world-knowledge`, `long-context`, `instruction-following`,
  `math`, `language-reasoning`, `coding`, `safety-and-grounding`, and
  `classic-language-modeling` (all level 1).

### METHODS
- id (PK), name, full_name, description, introduced_year
- source_url, source_title, code_snippet_url
- collection_name, collection_description, collection_parent
- area_id (FK), image_url, image_credit, slug (UNIQUE), keywords
- created_at, updated_at
- Indexes: area_id, keywords (GIN, partial), image_url (partial), slug unique

### DATASETS
- id (PK), name, full_name, description, url, hf_url
- short_description, homepage
- parent_dataset_id (FK self), image_url, thumbnail_url, verified_image_url
- introducing_paper_id (FK), introducing_paper_title, paper_url
- license_name, license_url
- introduced_date, introduced_year
- modalities (JSONB), languages (JSONB), variants (JSONB)
- num_papers (default 0), warning, pwc_url
- slug (UNIQUE, NOT NULL)
- variant_type (CHECK in [split, variant, subset, derived, augmented]), split_name
- created_at, updated_at
- Indexes: slug, parent_dataset_id, name, introduced_year/date, num_papers DESC, full-text over description/short_description

### EVALUATIONS
- id (PK)
- paper_id (FK), task_id (FK), dataset_id (FK)
- model_name, harness (optional), methodology, metrics (JSONB)
- uses_additional_data (bool), best_rank, best_metric (string), evaluated_on, external_source_url
- created_at, updated_at
- Indexes: GIN(metrics), (paper_id, task_id, dataset_id), (task_id, dataset_id, best_metric)
- **Hierarchy semantics:** `task_id` may reference any task in the hierarchy
  (top-level or any child subtask), but each evaluation belongs to exactly one
  `(task_id, dataset_id, best_metric)` leaderboard. Use the most specific child
  task. Parent rollups are read-only via API filters
  (`?include_descendants=true`); rank recalculation always runs within a
  single leaderboard triple.

### METRICS
- id (PK), name (UNIQUE), full_name
- direction CHECK in ('higher_is_better','lower_is_better')
- description, created_at, updated_at
- Indexes: name

### REPOSITORIES
- id (PK), url (UNIQUE), owner, name
- num_stars, num_stars_updated_at
- trending_score (double precision), trending_score_updated_at
- source, created_at, updated_at
- Indexes: url unique, owner, name, num_stars DESC, created/updated, trending (score, updated_at), num_stars_updated_at

### REPOSITORY_STAR_HISTORY
- id (PK)
- repository_id (FK), num_stars, snapshot_at (timestamp, NOT NULL)
- created_at
- Unique: (repository_id, snapshot_at)
- Indexes: repository_id, snapshot_at DESC, composite for recent queries

### PROJECT_PAGES
- id (PK), url, is_official, source, created_at, updated_at
- Indexes: url, is_official, source

### USER_BOOKMARKS
- hf_username VARCHAR(255), paper_id BIGINT (FK papers, ON DELETE CASCADE), created_at TIMESTAMPTZ DEFAULT now()
- Primary key: (hf_username, paper_id)
- Indexes: idx_user_bookmarks_user (hf_username), idx_user_bookmarks_paper (paper_id)

## Junction Tables

- PAPER_AUTHORS(paper_id, author_id, author_order > 0) PK(paper_id, author_id)
- PAPER_TASKS(paper_id, task_id) PK(paper_id, task_id)
- PAPER_METHODS(paper_id, method_id) PK(paper_id, method_id)
- PAPER_DATASETS(paper_id, dataset_id) PK(paper_id, dataset_id)
- PAPER_REPOSITORIES(paper_id, repository_id, is_official) PK(paper_id, repository_id)
- PAPER_PROJECT_PAGES(paper_id, project_page_id) PK(paper_id, project_page_id)
- TASK_DATASETS(task_id, dataset_id, featured_rank, supports_harness, created_at, updated_at) PK(task_id, dataset_id)
- TASK_DATASET_METRICS(task_id, dataset_id, metric_id, created_at) PK(task_id, dataset_id, metric_id)
- USER_BOOKMARKS(hf_username, paper_id, created_at) PK(hf_username, paper_id) — user-scoped state, not a cross-entity junction. Keyed on the lowercased HF username carried in the `pwc_session` JWT; rows are removed via `ON DELETE CASCADE` when the underlying paper is deleted.

**Note:** TASK_DATASETS owns task-specific *display metadata* (featured ordering, harness support) for a (task, dataset) pair. TASK_DATASET_METRICS defines the actual leaderboards by adding the metric dimension. Together they replace the legacy single-table design: TASK_DATASETS is what task pages render benchmark cards from, and TASK_DATASET_METRICS is what evaluation create/update validates against. Both tables key on `task_id`, which means subtasks (child tasks under `tasks.parent_id`) own benchmarks and leaderboards independently from their parent.


## Views (current)

- authors_with_paper_count — aggregation for authors
- latest_papers — only latest versions
- cs_papers — latest + cs.% filter
- base_datasets — only base datasets (no parent)
- dataset_hierarchies — recursive tree with levels and path
- datasets_with_parent — handy join view
- project_pages_api — updatable view over project_pages (INSTEAD OF triggers)
- papers_with_authors — present (grants)

## Functions & Triggers

- update_updated_at_column() — BEFORE UPDATE sets updated_at on: areas, authors, datasets, methods, papers, tasks, evaluations
- project_pages_api_{insert,update,delete}() — maintain project_pages_normalized via view triggers
- calculate_star_velocity(repository_id, hours_lookback=24)
- calculate_trending_score(repository_id, hours_lookback=24, recency_weight=2.0)

## Notes & Guidance

- **Leaderboards:** TASK_DATASET_METRICS defines all valid leaderboards. A (task, dataset, metric) triple must exist before evaluations can be added; `evaluation_service` enforces this. Rank recalculation always runs within a single `(task_id, dataset_id, best_metric)` triple.
- **Task-Dataset Relationships:** TASK_DATASETS holds membership and display metadata (featured ordering, harness support) per (task, dataset) pair, while TASK_DATASET_METRICS holds the metric dimension. Both tables exist in production; do not fall back to the older "infer task-dataset from metrics" pattern.
- **Subtasks (task hierarchy):** subtasks are first-class child rows in TASKS connected via `parent_id`. Each subtask owns its own task pages, benchmarks (TASK_DATASETS rows), leaderboards (TASK_DATASET_METRICS rows), and EVALUATIONS. To roll up subtasks for a parent task page, the API exposes `?include_descendants=true` on `/api/v1/datasets/?task=...` and `/api/v1/evaluations/?task_id=...`. Writes always target the most-specific child task so rank semantics stay clean.
- **Project pages:** is_official is stored on PROJECT_PAGES (not in the junction); associate via PAPER_PROJECT_PAGES.
- **Repositories:** single row per URL (normalized), paper association via PAPER_REPOSITORIES with per-paper is_official; trending fields support hourly trending calculations backed by REPOSITORY_STAR_HISTORY.
- **User bookmarks:** persisted per HF account in USER_BOOKMARKS; written exclusively through `/api/v1/me/bookmarks` endpoints which require the `pwc_session` cookie.

This document is synchronized with the live schema via schema dump and table descriptions.
