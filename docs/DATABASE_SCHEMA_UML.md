# PapersWithCode - Database Schema & UML (Live, July 2026)

## Overview

This document reflects the current PostgreSQL schema of the PapersWithCode backend as of July 2026. It is kept aligned with the SQLAlchemy models and migrations; verify against the database before making production schema changes.

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

┌──────────────────────────────┐
│       PAPER_RELATIONS        │
├──────────────────────────────┤
│ source_paper_id (FK papers)  │◄──── PAPERS.id (predecessor, ON DELETE CASCADE)
│ target_paper_id (FK papers)  │◄──── PAPERS.id (successor,   ON DELETE CASCADE)
│ created_at                   │
│ PK (source_paper_id, target_paper_id)
│ CHECK source_paper_id <> target_paper_id
└──────────────────────────────┘

┌──────────────────────────────┐
│      TASK_SISTER_TASKS       │
├──────────────────────────────┤
│ task_id (FK tasks)           │◄──── TASKS.id (the task page, ON DELETE CASCADE)
│ sister_task_id (FK tasks)    │◄──── TASKS.id (a sibling shown, ON DELETE CASCADE)
│ display_order (INT, default 0)
│ created_at                   │
│ PK (task_id, sister_task_id) │
│ CHECK task_id <> sister_task_id
└──────────────────────────────┘

┌─────────────────┐     ┌───────────────────────┐
│  CONFERENCES    │     │  PAPER_CONFERENCES    │
├─────────────────┤     ├───────────────────────┤
│ id (PK)         │◄────┤ conference_id (FK)    │
│ name            │     │ paper_id (FK)         │◄── PAPERS.id
│ slug (UNIQUE)   │     │ source                │
│ short_name      │     │ PK (paper, conference)│
│ year            │     └───────────────────────┘
│ url             │
│ start_date      │
│ end_date        │
│ venue, location │
│ description     │
│ created/updated │
└─────────────────┘

┌─────────────────┐     ┌────────────────────────────┐
│  ORGANIZATIONS  │     │   PAPER_ORGANIZATIONS      │
├─────────────────┤     ├────────────────────────────┤
│ id (PK)         │◄────┤ organization_id (FK)       │
│ name            │     │ paper_id (FK)              │◄── PAPERS.id
│ slug (UNIQUE)   │     │ source                     │
│ hf_url          │     │ PK (paper, organization)   │
│ logo_url        │     └────────────────────────────┘
│ website_url     │
│ github_url      │
│ description     │
│ created/updated │
└─────────────────┘

┌──────────────────────────────┐
│    PENDING_PAPER_EDITS       │
├──────────────────────────────┤
│ id (PK)                      │
│ paper_id (FK papers)         │◄──── PAPERS.id (ON DELETE CASCADE)
│ hf_username                  │
│ is_author (bool)             │
│ edit_type (CHECK in [tasks,  │
│   methods, evaluations,      │
│   repositories, project_pages])
│ proposed_payload (JSONB)     │
│ current_payload (JSONB, NULL)│
│ status (CHECK in [pending,   │
│   approved, rejected])       │
│ admin_note, reviewed_by      │
│ created_at, updated_at,      │
│ reviewed_at                  │
└──────────────────────────────┘
```

## Additional current tables

The main diagram above predates a few tables added for Hugging Face trending,
conference scheduling, and account preferences:

```text
HF_ARTIFACTS
  id (PK), kind (model|dataset|space), repo_id, url
  trending_score, likes, downloads, fetched_at, created_at, updated_at
  UNIQUE(kind, repo_id)

PAPER_HF_ARTIFACTS
  paper_id (FK papers), hf_artifact_id (FK hf_artifacts), created_at
  PK(paper_id, hf_artifact_id)

CONFERENCE_DEADLINES
  id (PK), conference_id (FK conferences), deadline_type, label
  deadline_at, timezone, created_at, updated_at

USER_PREFERENCES
  hf_username (PK), hide_closed_source_evals, created_at, updated_at
```

## Core Tables (DDL highlights)

The following summarizes the live structure. See the database for full DDL.

### PAPERS
- id (PK), title, abstract
- source (arxiv|external), source_url (required for external rows)
- arxiv_id, version, is_latest_version
- date_published, proceeding, conference, conference_url_abs, conference_url_pdf
- citation_count, semantic_scholar_id, citation_updated_at
- primary_category, all_categories[], urls_extracted
- methods_scanned_at, thumbnail_url
- hf_models[], hf_datasets[], hf_spaces[]
- trending_score, trending_score_updated_at, github_trending_component
- hf_trending_component, hf_artifacts_scanned_at
- tldr (TEXT, NULL — frontend v2 TL;DR panel; no generation pipeline yet)
- num_pages (INTEGER, NULL — source PDF page count; not surfaced in UI yet)
- created_at, updated_at
- Indexes: title/abstract full-text, arxiv_id, date, conference, latest flag, version, citation count, categories, urls_extracted (incl. partial cs.% index)
- **Submission provenance:** original paper creation does not currently store a submitter. External papers can be created through the public submit flow or the external-resource ingestion endpoints, but `papers` has no `submitted_by_hf_username`/`submitted_via` fields and there is no paper-submission audit table. `pending_paper_edits.hf_username` only tracks later metadata edit submissions, not who originally indexed a paper.

### AUTHORS
- id (PK), name (CHECK name not empty)
- hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro
- created_at, updated_at

### AREAS
- id (PK), name, description, created_at, updated_at

### TASKS
- id (PK), name, description, slug (UNIQUE)
- parent_id (FK self), area_id (FK), level (default 0)
- research_trends (JSONB), is_visible (bool)
- keywords, image_url, image_credit, useful_leaderboards
- image_data (BYTEA, NULL), image_mime_type (VARCHAR(100), NULL) — DB-backed hero image bytes; ORM defers `image_data` so list queries never load the blob; `image_mime_type` doubles as the "has DB image" flag
- created_at, updated_at
- Indexes: parent_id, area_id, slug
- **Images:** curated self-hosted heroes are stored in `image_data`/`image_mime_type` and served at `/api/v1/tasks/{slug}/image`. The API resolves `image_url` to that endpoint when `image_mime_type` is set; otherwise it falls back to the stored external `image_url`.
- **Hierarchy:** subtasks are child rows linked through `parent_id`. `level`
  is `0` for top-level tasks, `1` for subtasks under a top-level task,
  `2` for sub-subtasks, etc. Each subtask has its own page, description,
  benchmarks, and evaluations. Example: `language-modeling` (level 0) has
  child subtasks `world-knowledge`, `long-context`, `instruction-following`,
  `math`, `language-reasoning`, `coding`, `safety-and-grounding`, and
  `classic-language-modeling` (all level 1).
- **Sister tasks:** the "Sister Tasks" sidebar on a task page is driven by the
  explicit `task_sister_tasks` table, not by `area_id`. `area_id` only groups
  tasks for the taxonomy index and search; the curated sister list is
  per-task and ordered by `display_order`.

### METHODS
- id (PK), name, full_name, description, introduced_year
- source_paper_id (FK papers), source_url, source_title, code_snippet_url
- collection_name, collection_description, collection_parent
- area_id (FK), image_url, image_credit, slug (UNIQUE), keywords
- image_data (BYTEA, NULL), image_mime_type (VARCHAR(100), NULL) — DB-backed figure bytes (deferred in ORM); served at `/api/v1/methods/{slug}/image` when populated
- created_at, updated_at
- Indexes: area_id, keywords (GIN, partial), image_url (partial), slug unique
- **Images:** same DB-first / external-fallback semantics as TASKS (`entity_image_url` in `backend/utils/entity_images.py`).

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
- uses_additional_data (bool), is_open (bool), best_rank, best_metric (string)
- evaluated_on, external_source_url
- num_parameters (BIGINT, NULL — raw model parameter count, e.g. 7000000000 for a 7B model; non-negative CHECK)
- hf_model_url (TEXT, NULL — Hugging Face model page for the evaluated model, e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3; CHECK must start with https://huggingface.co/)
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

### CONFERENCES
- id (PK), name, slug (UNIQUE NOT NULL), short_name, year
- url, start_date, end_date, venue, location, description
- image_url, image_credit — external fallback URLs / attribution
- image_data (BYTEA, NULL), image_mime_type (VARCHAR(100), NULL) — DB-backed hero bytes (deferred in ORM); served at `/api/v1/conferences/{slug}/image` when populated
- hf_url, tier, tags[], country, city
- created_at, updated_at
- Indexes: slug, year DESC

### PAPER_CONFERENCES
- paper_id (FK papers ON DELETE CASCADE), conference_id (FK conferences ON DELETE CASCADE), source VARCHAR(16) DEFAULT 'manual', award
- PK (paper_id, conference_id)
- Indexes: conference_id, paper_id

### CONFERENCE_DEADLINES
- id (PK), conference_id (FK conferences ON DELETE CASCADE)
- deadline_type, label, deadline_at, timezone
- created_at, updated_at
- Indexes: conference_id, deadline_at

### ORGANIZATIONS
- id (PK), name, slug (UNIQUE NOT NULL)
- hf_url, logo_url, website_url, github_url, description
- created_at, updated_at
- Indexes: slug
- Normalized organization rows (NVIDIA, Google, Meta, ...), sourced primarily from Hugging Face org profiles. Used to tag papers by the lab/company behind them and to power organization pages (e.g. `/nvidia`).

### PAPER_ORGANIZATIONS
- paper_id (FK papers ON DELETE CASCADE), organization_id (FK organizations ON DELETE CASCADE), source VARCHAR(32) DEFAULT 'manual'
- PK (paper_id, organization_id)
- Indexes: organization_id, paper_id

### PENDING_PAPER_EDITS
- id BIGSERIAL (PK)
- paper_id BIGINT (FK papers, ON DELETE CASCADE)
- hf_username VARCHAR(255) — lowercased HF username from `pwc_session`
- is_author BOOLEAN DEFAULT FALSE — true when submitter is a linked author of `paper_id` at submit time
- edit_type VARCHAR(32) CHECK in [tasks, methods, evaluations, repositories, project_pages, source_url, hf_artifacts, new_task, new_method, new_benchmark, new_metric]
- proposed_payload JSONB — shape matches the matching admin mutation endpoint
- current_payload JSONB NULL — snapshot of live data at submit time for review diffing
- status VARCHAR(16) DEFAULT 'pending' CHECK in [pending, approved, rejected]
- admin_note TEXT, reviewed_by VARCHAR(255), reviewed_at TIMESTAMPTZ
- created_at, updated_at TIMESTAMPTZ DEFAULT now()
- Indexes: (status, created_at DESC), (paper_id, edit_type), (hf_username), partial (is_author) WHERE status='pending'

## Junction Tables

- PAPER_AUTHORS(paper_id, author_id, author_order > 0) PK(paper_id, author_id)
- PAPER_TASKS(paper_id, task_id) PK(paper_id, task_id)
- PAPER_METHODS(paper_id, method_id) PK(paper_id, method_id)
- PAPER_DATASETS(paper_id, dataset_id) PK(paper_id, dataset_id)
- PAPER_REPOSITORIES(paper_id, repository_id, is_official) PK(paper_id, repository_id)
- PAPER_HF_ARTIFACTS(paper_id, hf_artifact_id, created_at) PK(paper_id, hf_artifact_id)
- PAPER_PROJECT_PAGES(paper_id, project_page_id) PK(paper_id, project_page_id)
- PAPER_RELATIONS(source_paper_id, target_paper_id, created_at) PK(source_paper_id, target_paper_id) — directed lineage edges between papers. `source_paper_id` is the predecessor (earlier) paper and `target_paper_id` is the successor (follow-up) paper, e.g. DINOv2 -> DINOv3. CHECK constraint prevents self-edges; both FKs cascade on paper delete. Many-to-many in both directions: a paper can have multiple successors and multiple predecessors.
- TASK_SISTER_TASKS(task_id, sister_task_id, display_order, created_at) PK(task_id, sister_task_id) — explicit, ordered sister-task relationships rendered on a task page's sidebar. `task_id` is the page; `sister_task_id` is a task shown in that page's "Sister Tasks" list, sorted by `display_order` (ascending, 0 first). Directed and NOT automatically symmetric (configuring B on A's page does not add A to B's page). CHECK prevents self-edges; both FKs cascade on task delete. This replaces the previous behavior of deriving sisters from every visible task sharing the same `area_id`.
- PAPER_CONFERENCES(paper_id, conference_id, source, award) PK(paper_id, conference_id) — links papers to normalized conference rows. `source` is `manual` (import scripts / admin) or `auto`; `award` stores an optional conference award label. Display tags such as "CVPR 2026" on paper pages still use the denormalized `papers.proceeding` column alongside this junction.
- PAPER_ORGANIZATIONS(paper_id, organization_id, source) PK(paper_id, organization_id) — links papers to normalized organization rows (e.g. NVIDIA). `source` is `manual` (admin) or an importer tag such as `hf_org_papers`. Powers org logo tags on paper pages and organization pages like `/nvidia`.
- TASK_DATASETS(task_id, dataset_id, supports_harness, created_at, updated_at) PK(task_id, dataset_id)
- TASK_DATASET_METRICS(task_id, dataset_id, metric_id, created_at) PK(task_id, dataset_id, metric_id)
- USER_BOOKMARKS(hf_username, paper_id, created_at) PK(hf_username, paper_id) — user-scoped state, not a cross-entity junction. Keyed on the lowercased HF username carried in the `pwc_session` JWT; rows are removed via `ON DELETE CASCADE` when the underlying paper is deleted.
- USER_PREFERENCES(hf_username, hide_closed_source_evals, created_at, updated_at) PK(hf_username) — per-account display preferences.
- PENDING_PAPER_EDITS(id, paper_id, hf_username, is_author, edit_type, proposed_payload, current_payload, status, admin_note, reviewed_by, created_at, updated_at, reviewed_at) PK(id) — non-admin edit submissions awaiting admin approval. Approval applies `proposed_payload` through the same backend mutation services that admin direct edits use; rejected/pending rows never affect live data.

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

- update_updated_at_column() — BEFORE UPDATE sets updated_at on: areas, authors, conferences, conference_deadlines, datasets, methods, papers, tasks, evaluations
- project_pages_api_{insert,update,delete}() — maintain project_pages_normalized via view triggers
- calculate_star_velocity(repository_id, hours_lookback=24)
- calculate_trending_score(repository_id, hours_lookback=24, recency_weight=2.0)

## Notes & Guidance

- **Leaderboards:** TASK_DATASET_METRICS defines all valid leaderboards. A (task, dataset, metric) triple must exist before evaluations can be added; `evaluation_service` enforces this. Rank recalculation always runs within a single `(task_id, dataset_id, best_metric)` triple.
- **Task-Dataset Relationships:** TASK_DATASETS holds membership and display metadata (featured ordering, harness support) per (task, dataset) pair, while TASK_DATASET_METRICS holds the metric dimension. Both tables exist in production; do not fall back to the older "infer task-dataset from metrics" pattern.
- **Subtasks (task hierarchy):** subtasks are first-class child rows in TASKS connected via `parent_id`. Each subtask owns its own task pages, benchmarks (TASK_DATASETS rows), leaderboards (TASK_DATASET_METRICS rows), and EVALUATIONS. To roll up subtasks for a parent task page, the API exposes `?include_descendants=true` on `/api/v1/datasets/?task=...` and `/api/v1/evaluations/?task_id=...`. Writes always target the most-specific child task so rank semantics stay clean.
- **Project pages:** is_official is stored on PROJECT_PAGES (not in the junction); associate via PAPER_PROJECT_PAGES.
- **Repositories:** single row per URL (normalized), paper association via PAPER_REPOSITORIES with per-paper is_official; trending fields support hourly trending calculations backed by REPOSITORY_STAR_HISTORY.
- **User preferences and bookmarks:** persisted per HF account in USER_PREFERENCES and USER_BOOKMARKS; written through `/api/v1/me/preferences` and `/api/v1/me/bookmarks`, which require the `pwc_session` cookie.
- **Pending paper edits:** non-admin edit submissions for paper-page surfaces (tasks, methods, evaluations, repositories, project pages) are written to PENDING_PAPER_EDITS through `/api/v1/me/paper-edits`. Admin direct edits bypass this table and continue mutating live data through the existing `/api/v1/papers/{id}/...` and `/api/v1/evaluations/...` admin endpoints. Approval of a pending row replays `proposed_payload` through the shared mutation services so live data only changes after admin confirmation.
- **Original paper submissions:** unlike pending edits, original paper creation is not attributed to a user today. `/api/v1/papers/submit` and `/api/v1/papers/external/from-url` create or reuse `papers` rows without persisting the authenticated Hugging Face username, request source, or raw submission payload. Add a dedicated submission audit table or nullable provenance columns before relying on submitter identity for moderation, attribution, or abuse analysis.
- **Paper lineage:** directed predecessor/successor edges between papers live in PAPER_RELATIONS (`source_paper_id` -> `target_paper_id`, predecessor -> successor). Surfaced on the paper detail API via `predecessor_papers` and `successor_papers`, and rendered as the lineage banner on the paper detail view (e.g. DINOv2 shows DINOv3 as the follow-up; DINOv3 shows DINOv2 as the predecessor).
- **Entity images (tasks, methods, conferences):** curated hero/figure images live in SQL (`image_data` + `image_mime_type`), not in `frontend/public`. Seed PNGs for import live under `data/entity_image_seeds/{tasks,methods,conferences}/` and are loaded with `backend/database/import_entity_image.py` or bulk backfill via `run_add_entity_image_data.py`. Browser-only assets (favicons, `og-image.png`, logos) remain static under `frontend/public`. Datasets and papers still use URL columns (`image_url`, `thumbnail_url`, etc.) — they are not DB-blob backed today.

Keep this document aligned with `backend/models/database.py` and the migrations in
`backend/database/migrations/`. The live database remains authoritative when
models and migrations disagree.
