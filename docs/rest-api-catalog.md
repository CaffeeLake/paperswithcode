# REST API catalog

Base URL: `http://localhost:8000/api/v1/` (production: `https://paperswithcode.co/api/v1/`).

List endpoints generally support pagination, filtering, and search; see `docs/backend-api.md` for conventions.

## Papers (`/api/v1/papers/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/papers/` | GET | Paginated list with filtering (search, date, conference, etc.) |
| `/papers/{paper_id}` | GET | Get paper by database ID |
| `/papers/arxiv/{arxiv_id}` | GET | Get paper by ArXiv ID (latest version) |
| `/papers/arxiv/{arxiv_id}?version=v2` | GET | Get specific version of a paper |
| `/papers/arxiv/{arxiv_id}/versions` | GET | Get all versions of a paper |
| `/papers/search` | GET | Full-text search with citation-based ranking |
| `/papers/recent` | GET | Recently published papers |
| `/papers/trending` | GET | Trending papers (star velocity) |
| `/papers/stats` | GET | Database statistics |

**Example**: `curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=10"`

## Datasets (`/api/v1/datasets/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/datasets/` | GET | List datasets with pagination and filtering |
| `/datasets/` | POST | Create new dataset (auto-generates slug, links to tasks) |
| `/datasets/{dataset_id}` | GET | Get specific dataset details |
| `/datasets/{dataset_id}/evaluations` | GET | Get evaluations for dataset |

**Subtask rollups**: pass `task=<slug-or-id>&include_descendants=true` to roll
up datasets owned by every subtask under the given task. Useful for parent
task pages such as `/tasks/language-modeling` whose benchmarks now live on
its child subtasks (`world-knowledge`, `math`, ...).

**Creating a dataset**:
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Video-MMLU",
    "full_name": "Video-MMLU: Massive Multi-Discipline Lecture Understanding",
    "description": "Comprehensive benchmark for evaluating LMMs",
    "url": "https://enxinsong.com/Video-MMLU-web/",
    "hf_url": "https://huggingface.co/datasets/Enxin/Video-MMLU",
    "paper_url": "https://arxiv.org/abs/2504.14693",
    "task_ids": [9]
  }'
```

## Evaluations (`/api/v1/evaluations/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/evaluations/` | GET | List evaluations with filtering |
| `/evaluations/` | POST | Add evaluation result (auto-calculates ranks) |
| `/evaluations/{evaluation_id}` | GET | Get specific evaluation |
| `/evaluations/{evaluation_id}` | PUT | Update evaluation result |
| `/evaluations/{evaluation_id}` | DELETE | Delete evaluation result |
| `/evaluations/recalculate-ranks` | POST | Recalculate leaderboard ranks |

**Task hierarchy**: leaderboards key off the most-specific task. When a task
has subtasks, write evaluations against the child task and read them back
either via the child `task_id` or, for parent rollups, via
`?task_id=<parent>&include_descendants=true`. Rank recalculation always runs
within a single `(task_id, dataset_id, best_metric)` triple.

**Adding an evaluation**:
```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 123,
    "task_id": 12,
    "dataset_id": 138,
    "model_name": "DETR-R50",
    "metrics": {"AP": "44.9", "AP50": "64.7"},
    "best_metric": "AP",
    "methodology": "End-to-End Object Detection with Transformers"
  }'
```

## Tasks (`/api/v1/tasks/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks/` | GET | List AI/ML tasks with hierarchical filtering |
| `/tasks/{task_id}` | GET | Get specific task details |
| `/tasks/{task_id}/papers` | GET | Get papers for task |
| `/tasks/{task_id}/datasets` | GET | Get datasets for task |
| `/tasks/{task_id}/children` | GET | Get child tasks (subtasks) |
| `/tasks/{task_id}/parents` | GET | Get parent task chain up to the root |
| `/tasks/{task_id}/keywords` | PUT | Update task keywords |

**Query parameters**: `q` (search), `area_id`, `parent_id`, `level`, `ordering`

**Subtasks model**: subtasks are first-class child rows in the `tasks` table
linked via `tasks.parent_id` (with `tasks.level = parent.level + 1`). Each
subtask has its own description, page, benchmarks, and evaluations. Parent
task pages render their subtasks via `/tasks/{task_id}/children`. Example:
Language Modeling (`language-modeling`, level 0) is the parent of
`world-knowledge`, `long-context`, `instruction-following`, `math`,
`language-reasoning`, `coding`, `safety-and-grounding`, and
`classic-language-modeling` (all level 1).

## Methods (`/api/v1/methods/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/methods/` | GET | List AI/ML methods (e.g., ResNet, Transformer, Adam) |
| `/methods/{method_id}` | GET | Get specific method details |
| `/methods/{method_id}/papers` | GET | Get papers using this method |
| `/methods/{method_id}/keywords` | PUT | Update method keywords |

**Query parameters**: `q` (search), `name`, `full_name`, `introduced_year`, `ordering`

## Areas (`/api/v1/areas/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/areas/` | GET | List research areas (Computer Vision, NLP, etc.) |
| `/areas/{area_id}` | GET | Get specific area details |
| `/areas/{area_id}/tasks` | GET | Get tasks in this area |
| `/areas/{area_id}/papers` | GET | Get papers in this area |

## Authors (`/api/v1/authors/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/authors/` | GET | List authors with Hugging Face integration |
| `/authors/{author_id}` | GET | Get specific author details |
| `/authors/{author_id}/papers` | GET | Get papers by author |

**Query parameters**: `search` (name or HF username), `hf_users_only`

## Repositories (`/api/v1/repositories/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/repositories/` | GET | List GitHub repositories with star counts |
| `/repositories/{repository_id}` | GET | Get specific repository details |
| `/repositories/{repository_id}/papers` | GET | Get papers linked to repository |

**Query parameters**: `owner`, `official_only`, `min_stars`, `source`, `order_by`

## Metrics (`/api/v1/metrics/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics/` | GET | List evaluation metrics (AP, WER, BLEU, etc.) |
| `/metrics/{metric_id}` | GET | Get specific metric details |

## Thumbnails (`/api/thumbnails/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/thumbnails/{filename}` | GET | Serve paper thumbnail images |
| `/thumbnails/status/{paper_id}` | GET | Check whether a generated thumbnail exists |
| `/thumbnails/generate/{paper_id}` | POST | Queue thumbnail generation for a paper |

Note: thumbnails are mounted without the `/api/v1` prefix in the main app. In
production, `/api/thumbnails/` remains the browser-facing endpoint while the
canonical JPEGs can be stored in a private Hugging Face Storage Bucket and
proxied server-side with `PWC_HF_TOKEN`.

## Cron (`/api/v1/cron/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cron/status` | GET | Get status of all CRON jobs |
| `/cron/job/{job_name}` | GET | Get specific job status |
| `/cron/health` | GET | Health endpoint for monitoring |

For day-to-day automation, see `docs/operations.md` and `.github/workflows/scripts/README.md`.

## Working with data (API-first)

Prefer HTTP APIs over raw SQL: validation, slugs, ranks, and associations stay consistent. Detailed curl workflows, metric rules, and bulk imports: **`docs/data-workflows.md`**.

**Query papers**:
```bash
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=10"
curl "http://localhost:8000/api/v1/papers/?published_after=2023-01-01&conference=NeurIPS"
curl "http://localhost:8000/api/v1/papers/trending?limit=20"
```
