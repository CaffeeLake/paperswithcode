# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Essentials: Python

Do not write SUMMARY.md files to summarize code changes. Just implement the code.

Run anything where you need to proceed with further work as a background task in Cursor.

**ALWAYS use `uv run --env-file backend/keys.env` when running Python scripts.** This ensures you use the correct environment variables and virtual environment.

Replace statements like `DBPaper.is_latest_version == True` by just `DBPaper.is_latest_version`. Similarly, when you need to write something like `DBPaper.urls_extracted == False`, write `~DBPaper.urls_extracted` instead.

To authenticate and connect to the PostgreSQL database, see `docs/POSTGRESQL_GUIDE.md` for details.

**Hardware**: Everything runs on a Hetzner VPS with 4GB of RAM and 80GB of disk space. Many scripts are optimized to deal with low RAM constraints.

The backend and frontend can be run using the `start_services.sh` bash script. They can be stopped using the `stop_services.sh` bash script.

**The backend API includes a v1 in its URL: use `http://localhost:8000/api/v1/`**

## Project Overview

Paperswithcode.ai is a complete recreation of paperswithcode.com built with modern web technologies. The project consists of a **React frontend** and a **FastAPI backend** with a comprehensive REST API, backed by a PostgreSQL database.

The data was populated from papers indexed at huggingface.co/papers and enriched with the legacy PapersWithCode data dump (2.2GB papers, repository links + 236MB evaluation tables, see the `/data/legacy_pwc_data/` folder).

The data is continuously enriched using **CRON jobs** (`cron/` folder) that add new papers from Hugging Face, update GitHub repository stars, update citation counts, and extract GitHub URLs and project pages using AI.

**Tech Stack**:
- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS + TanStack Query + React Router v6
- **Backend**: FastAPI with 11 API routers, service layer architecture, SQLAlchemy ORM
- **Database**: PostgreSQL with full-text search indexes
- **GenAI**: OpenRouter/Google Gemini for URL extraction from PDFs
- **CRON System**: Hourly and daily jobs for data enrichment
- **Package Management**: uv for Python dependencies, npm for frontend

## Essential Commands

### Backend API Commands (in root directory)

```bash
# Start the FastAPI backend server
uv run --env-file backend/keys.env backend/run_server.py

# Or use uvicorn directly
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Test API endpoints
curl "http://localhost:8000/api/v1/papers/recent?limit=5"
curl "http://localhost:8000/api/v1/papers/search?q=transformer"
curl "http://localhost:8000/api/v1/datasets/"

# View interactive API documentation
open http://localhost:8000/docs
```

### Frontend Commands (in `frontend/` directory)

```bash
# Development
npm run dev          # Start development server
npm run build        # Production build
npm run build:dev    # Development build
npm run preview      # Preview production build
npm run lint         # Run ESLint (ALWAYS run before committing)
```

### Python/Database Commands (in root directory)

```bash
# Package management
uv add package_name  # Add Python dependency (updates pyproject.toml)
uv sync             # Install/sync dependencies from lock file

# Database setup
psql -U postgres -d paperswithcode_hf -f backend/database/papers_setup/setup_database.sql

# Run database migration/setup scripts
uv run --env-file backend/keys.env python backend/database/papers_setup/add_hf_papers.py

# Test backend
uv run --env-file backend/keys.env python backend/tests/test_authors_api.py
```

### CRON Job Commands (in root directory)

```bash
# View comprehensive status of all CRON jobs (RECOMMENDED)
uv run --env-file backend/keys.env cron/manage_cron.py summary

# List available CRON jobs
uv run --env-file backend/keys.env cron/manage_cron.py list

# Test a specific CRON job before scheduling
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations

# Check status of specific job
uv run --env-file backend/keys.env cron/manage_cron.py status import_hf_daily_papers

# Clean up old log files
uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

## Architecture & Code Organization

### Project Structure

```
paperswithcode/
├── backend/                    # FastAPI backend application
│   ├── main.py                # FastAPI app entry point (11 routers)
│   ├── config.py              # Configuration management
│   ├── run_server.py          # Development server runner
│   ├── models/                # Pydantic and SQLAlchemy models
│   │   ├── api.py            # Pydantic models for API requests/responses
│   │   ├── database.py       # SQLAlchemy ORM models
│   │   └── generators.py     # GenAI model configurations
│   ├── routers/               # FastAPI route handlers (11 routers)
│   │   ├── papers.py         # Paper endpoints
│   │   ├── datasets.py       # Dataset endpoints (POST/GET)
│   │   ├── evaluations.py    # Evaluation endpoints (POST/PUT/DELETE)
│   │   ├── tasks.py          # AI/ML tasks endpoints
│   │   ├── methods.py        # Methods/techniques endpoints
│   │   ├── areas.py          # Research areas endpoints
│   │   ├── authors.py        # Author endpoints
│   │   ├── repositories.py   # GitHub repository endpoints
│   │   ├── metrics.py        # Evaluation metrics endpoints
│   │   ├── thumbnails.py     # Paper thumbnail endpoints
│   │   └── cron.py           # CRON job status API
│   ├── services/              # Business logic layer (8+ services)
│   │   ├── paper_service.py
│   │   ├── dataset_service.py
│   │   ├── evaluation_service.py
│   │   ├── task_service.py
│   │   ├── method_service.py
│   │   ├── area_service.py
│   │   ├── author_service.py
│   │   ├── repository_service.py
│   │   ├── arxiv_service.py
│   │   ├── semantic_scholar_service.py
│   │   └── thumbnail_service.py
│   ├── database/              # Database setup and connection
│   │   ├── connection.py     # Database connection management
│   │   ├── README.md         # Database setup guide
│   │   ├── papers_setup/     # Paper import scripts
│   │   ├── authors_setup/    # Author data scripts
│   │   ├── tasks_setup/      # Task hierarchy scripts
│   │   ├── methods_setup/    # Methods data scripts
│   │   ├── datasets_setup/   # Dataset import scripts
│   │   ├── evaluations_setup/ # Evaluation data scripts
│   │   ├── repos_and_pages_setup/ # Repository and project page scripts
│   │   └── citations_setup/  # Citation tracking scripts
│   ├── utils/                 # Utility functions
│   │   ├── urls.py           # URL construction and validation
│   │   ├── exceptions.py     # Custom exception classes
│   │   ├── github_utils.py   # GitHub API utilities
│   │   ├── hf_utils.py       # Hugging Face API utilities
│   │   ├── pdf_utils.py      # PDF processing utilities
│   │   └── keyword_matching.py # Keyword extraction utilities
│   ├── genai_steps/           # GenAI extraction scripts
│   │   ├── extract_github_and_project_page_url.py
│   │   └── extract_orgs.py
│   └── tests/                 # Backend tests
│       ├── test_authors_api.py
│       ├── test_citation_search.py
│       └── test_rank_recalculation.py
├── frontend/                  # React frontend application
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   │   ├── ui/          # shadcn/ui components (don't edit manually)
│   │   │   ├── Header.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   ├── PaperCard.tsx
│   │   │   └── ...
│   │   ├── pages/            # Route components
│   │   │   ├── Index.tsx
│   │   │   ├── Papers.tsx
│   │   │   ├── PaperDetail.tsx
│   │   │   ├── TaskDetail.tsx
│   │   │   ├── MethodDetail.tsx
│   │   │   └── ...
│   │   ├── hooks/            # Custom React hooks
│   │   │   ├── usePapers.ts
│   │   │   ├── useDatasets.ts
│   │   │   ├── useEvaluations.ts
│   │   │   └── ...
│   │   ├── lib/              # Utility functions
│   │   │   ├── api.ts       # API client functions
│   │   │   └── utils.ts
│   │   └── utils/            # Additional utilities
│   ├── package.json
│   └── vite.config.ts
├── cron/                      # Automated CRON job scripts
│   ├── README.md             # Comprehensive CRON documentation
│   ├── hourly/               # High-performance hourly jobs (RECOMMENDED)
│   │   ├── update_github_stars.py      # 4,500 repos/hour
│   │   ├── update_citations.py         # 2,800 papers/hour
│   │   ├── extract_urls.py             # 50 papers/hour (AI-powered)
│   │   └── calculate_trending_scores.py
│   ├── daily/                # Legacy daily jobs
│   │   └── import_hf_daily_papers.py   # Import HF papers (Tue-Sat)
│   ├── manage_cron.py        # CRON management script
│   ├── logs/                 # CRON execution logs
│   └── utils/                # Shared CRON utilities
├── data/                      # Data files
│   ├── legacy_pwc_data/      # Original PapersWithCode data dump
│   │   ├── papers-with-abstracts.json (2.2GB)
│   │   ├── evaluation-tables.json (236MB)
│   │   ├── jul-28-datasets.json
│   │   ├── jul-28-methods.json
│   │   └── links-between-papers-and-code.json
│   ├── arxiv_papers_hf.csv   # Hugging Face papers export
│   └── paper_task_links_pwc/ # Task-paper associations
├── docs/                      # Comprehensive documentation
│   ├── API_GUIDE_ADDING_DATA.md
│   ├── ADDING_EVALUATIONS_GUIDE.md
│   ├── API_EXPANSION_PLAN.md
│   ├── POSTGRESQL_GUIDE.md
│   ├── AUTHORS_API_IMPLEMENTATION.md
│   └── ...
├── scripts/                   # Utility scripts
│   ├── export_tasks_to_csv.py
│   └── import_tasks_from_csv.py
├── pyproject.toml            # Python dependencies managed by uv
├── uv.lock                   # Lockfile for Python dependencies
├── start_services.sh         # Start backend + frontend
└── stop_services.sh          # Stop backend + frontend
```

### Frontend Core Structure

- **Entry Point**: `frontend/src/main.tsx` → `frontend/src/App.tsx` (routing setup)
- **Routing**: React Router v6 with routes defined in `frontend/src/App.tsx`
- **State Management**: TanStack Query for server state, React hooks for local state
- **Styling**: Tailwind CSS with custom design system and shadcn/ui components
- **API Client**: `frontend/src/lib/api.ts` - Uses fetch to communicate with backend

## API Endpoints: Complete Reference

The backend exposes a comprehensive REST API at `http://localhost:8000/api/v1/`. All endpoints support pagination, filtering, and search.

### Papers Router (`/api/v1/papers/`)

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

### Datasets Router (`/api/v1/datasets/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/datasets/` | GET | List datasets with pagination and filtering |
| `/datasets/` | POST | **Create new dataset** (auto-generates slug, links to tasks) |
| `/datasets/{dataset_id}` | GET | Get specific dataset details |
| `/datasets/{dataset_id}/evaluations` | GET | Get evaluations for dataset |

**Creating a dataset** (API-first approach):
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

### Evaluations Router (`/api/v1/evaluations/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/evaluations/` | GET | List evaluations with filtering |
| `/evaluations/` | POST | **Add evaluation result** (auto-calculates ranks) |
| `/evaluations/{evaluation_id}` | GET | Get specific evaluation |
| `/evaluations/{evaluation_id}` | PUT | **Update evaluation result** |
| `/evaluations/{evaluation_id}` | DELETE | **Delete evaluation result** |
| `/evaluations/recalculate-ranks` | POST | Recalculate leaderboard ranks |

**Adding an evaluation** (API-first approach):
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

### Tasks Router (`/api/v1/tasks/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks/` | GET | List AI/ML tasks with hierarchical filtering |
| `/tasks/{task_id}` | GET | Get specific task details |
| `/tasks/{task_id}/papers` | GET | Get papers for task |
| `/tasks/{task_id}/datasets` | GET | Get datasets for task |
| `/tasks/{task_id}/children` | GET | Get child tasks (subtasks) |
| `/tasks/{task_id}/keywords` | PUT | Update task keywords |

**Query parameters**: `q` (search), `area_id`, `parent_id`, `level`, `ordering`

### Methods Router (`/api/v1/methods/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/methods/` | GET | List AI/ML methods (e.g., ResNet, Transformer, Adam) |
| `/methods/{method_id}` | GET | Get specific method details |
| `/methods/{method_id}/papers` | GET | Get papers using this method |
| `/methods/{method_id}/keywords` | PUT | Update method keywords |

**Query parameters**: `q` (search), `name`, `full_name`, `introduced_year`, `ordering`

### Areas Router (`/api/v1/areas/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/areas/` | GET | List research areas (Computer Vision, NLP, etc.) |
| `/areas/{area_id}` | GET | Get specific area details |
| `/areas/{area_id}/tasks` | GET | Get tasks in this area |
| `/areas/{area_id}/papers` | GET | Get papers in this area |

### Authors Router (`/api/v1/authors/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/authors/` | GET | List authors with Hugging Face integration |
| `/authors/{author_id}` | GET | Get specific author details |
| `/authors/{author_id}/papers` | GET | Get papers by author |

**Query parameters**: `search` (name or HF username), `hf_users_only`

### Repositories Router (`/api/v1/repositories/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/repositories/` | GET | List GitHub repositories with star counts |
| `/repositories/{repository_id}` | GET | Get specific repository details |
| `/repositories/{repository_id}/papers` | GET | Get papers linked to repository |

**Query parameters**: `owner`, `official_only`, `min_stars`, `source`, `order_by`

### Metrics Router (`/api/v1/metrics/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics/` | GET | List evaluation metrics (AP, WER, BLEU, etc.) |
| `/metrics/{metric_id}` | GET | Get specific metric details |

### Thumbnails Router (`/api/thumbnails/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/thumbnails/{filename}` | GET | Serve paper thumbnail images |

### CRON Router (`/api/v1/cron/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cron/status` | GET | Get status of all CRON jobs |
| `/cron/jobs/{job_name}` | GET | Get specific job status |

## Working with Data: API-First Approach

**IMPORTANT**: When working with data, always prefer using the API endpoints over direct SQL queries. The API provides proper validation, error handling, automatic slug generation, and maintains data integrity.

### Adding Datasets

**Use the API** (RECOMMENDED):
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "COCO",
    "description": "Common Objects in Context dataset",
    "url": "https://cocodataset.org/",
    "task_ids": [1, 2, 3]
  }'
```

**Benefits**:
- Auto-generates URL-safe slug
- Validates task_ids exist
- Creates task-dataset associations
- Handles duplicate detection
- Returns complete dataset object

### Adding Evaluation Results

**Use the API** (RECOMMENDED):
```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 456,
    "task_id": 8,
    "dataset_id": 12,
    "metrics": {"WER": "5.2"},
    "best_metric": "WER",
    "model_name": "Whisper Large"
  }'
```

**Benefits**:
- Auto-calculates leaderboard ranks
- Validates paper_id, task_id, dataset_id exist
- Handles metric direction (higher/lower is better)
- Creates dataset-task association if missing
- Updates ranks for all competing evaluations

### Updating Evaluations

**Use the API** (RECOMMENDED):
```bash
curl -X PUT "http://localhost:8000/api/v1/evaluations/123" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": {"AP": "45.2", "AP50": "65.1"},
    "methodology": "Updated with better preprocessing"
  }'
```

### Querying Papers

**Use the API** (RECOMMENDED):
```bash
# Full-text search
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=10"

# Filter by date and conference
curl "http://localhost:8000/api/v1/papers/?published_after=2023-01-01&conference=NeurIPS"

# Get trending papers
curl "http://localhost:8000/api/v1/papers/trending?limit=20"
```

### Python API Usage

When writing Python scripts, use the service layer:

```python
from backend.database.connection import get_database_session
from backend.services.dataset_service import DatasetService
from backend.models.api import DatasetCreateRequest

def create_dataset():
    with get_database_session() as db:
        service = DatasetService(db)

        dataset_request = DatasetCreateRequest(
            name="Video-MMLU",
            description="Video understanding benchmark",
            url="https://example.com",
            task_ids=[9]
        )

        dataset = service.create_dataset(dataset_request)
        print(f"Created dataset: {dataset.slug}")
```

## CRON Jobs: Automated Data Enrichment

The project includes a sophisticated CRON system that continuously enriches the database. CRON jobs are located in `cron/` and managed via `cron/manage_cron.py`.

### Hourly Jobs (RECOMMENDED for Production)

Located in `cron/hourly/`. These are **significantly more efficient** than daily jobs:

#### 1. Update GitHub Stars (`update_github_stars.py`)
- **Schedule**: Every hour at :00
- **Performance**: 4,500 repositories/hour (108x faster than daily)
- **Scope**: All 50K+ repositories
- **Refresh Rate**: Every 7 days per repository
- **Features**:
  - Optimized rate limiting (0.8s delays, 90% of GitHub's 5K limit)
  - Deduplication by owner/name (saves 10-100x API calls)
  - Complete database update in ~15 hours vs. 66 days
- **Command**: `uv run --env-file backend/keys.env cron/hourly/update_github_stars.py`

#### 2. Update Citations (`update_citations.py`)
- **Schedule**: Every hour at :30
- **Performance**: 2,800 papers/hour (33x faster than daily)
- **Scope**: All papers with ArXiv IDs
- **Features**:
  - Optimized Semantic Scholar API rate limiting (1.3s delays)
  - Complete database update in ~19 hours vs. 27 days
  - Updates citation counts and citation_updated_at timestamp
- **Command**: `uv run --env-file backend/keys.env cron/hourly/update_citations.py`

#### 3. Extract GitHub URLs and Project Pages (`extract_urls.py`)
- **Schedule**: Every hour at :45
- **Performance**: 50 papers/hour (AI-powered)
- **Scope**: Papers from 2014 onwards without extracted URLs
- **Features**:
  - Uses OpenRouter AI models (Google Gemini) for intelligent extraction
  - Downloads and processes PDFs
  - Extracts GitHub repository URLs and project page URLs
  - Marks papers with `urls_extracted` flag to avoid reprocessing
  - Saves with source='ai_extraction' and is_official=True
  - Memory-optimized for 4GB RAM (batch size: 10)
- **API Requirements**: PWC_OPENROUTER_API_KEY in backend/keys.env
- **Command**: `uv run --env-file backend/keys.env cron/hourly/extract_urls.py`

#### 4. Calculate Trending Scores (`calculate_trending_scores.py`)
- **Schedule**: Every hour at :15
- **Performance**: 500 repositories/hour
- **Scope**: Recent papers (last 6 months)
- **Features**:
  - Tracks star velocity (stars gained per hour)
  - Stores historical snapshots in repository_star_history table
  - Calculates trending scores with recency weighting
  - Powers /api/v1/papers/trending endpoint
- **Command**: `uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py`

### Daily Jobs

Located in `cron/daily/`. Use for development/testing or lower API usage:

#### 1. Import Hugging Face Daily Papers (`import_hf_daily_papers.py`)
- **Schedule**: Tuesday to Saturday at 3:00 AM UTC
- **Purpose**: Import curated papers from Hugging Face API
- **Features**:
  - Fetches papers from previous day
  - Only runs Tue-Sat (papers submitted Mon-Fri on HF)
  - Populates papers, authors, repositories, and project_pages tables
  - Enriches author profiles with HF data (avatars, Pro status)
  - Extracts GitHub repository links and project pages
  - Smart duplicate prevention and author matching
- **Command**: `uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py`

### CRON Management

**View comprehensive status** (RECOMMENDED):
```bash
uv run --env-file backend/keys.env cron/manage_cron.py summary
```

This provides:
- System overview (available vs. active jobs)
- Performance metrics (success rates, health scores)
- Smart alerts (issue detection)
- Memory analysis
- Job details with recent history

**Other management commands**:
```bash
# List all available jobs
uv run --env-file backend/keys.env cron/manage_cron.py list

# Test a job before scheduling
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations

# Check status of specific job
uv run --env-file backend/keys.env cron/manage_cron.py status import_hf_daily_papers

# View logs
tail -f cron/logs/update_github_stars_$(date +%Y%m%d).log
```

### Setting Up CRON Jobs

Edit your crontab with `crontab -e`:

```bash
# PapersWithCode CRON Jobs - Hourly High-Performance Updates (RECOMMENDED)

# Import HF papers (Tue-Sat at 3:00 AM UTC)
0 3 * * 2-6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py

# Hourly GitHub stars update (4,500 repos/hour)
0 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/update_github_stars.py

# Hourly trending calculation (500 repos/hour)
15 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py

# Hourly citation update (2,800 papers/hour)
30 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/update_citations.py

# Hourly URL extraction (50 papers/hour, AI-powered)
45 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/extract_urls.py

# Clean up old logs weekly (Saturdays at 1:00 AM UTC)
0 1 * * 6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

**Performance with hourly jobs**:
- GitHub stars: Complete update in ~15 hours (vs. 66 days with daily)
- Citations: Complete update in ~19 hours (vs. 27 days with daily)
- URL extraction: 1,200 papers/day with AI-powered extraction
- Trending snapshots: ~12,000 snapshots/day

For more details, see `cron/README.md`.

## GenAI Features: URL Extraction

The project uses AI to extract GitHub repository URLs and project page URLs from research papers:

### URL Extraction Process

1. **AI-Powered PDF Analysis**: Uses OpenRouter (Google Gemini) to analyze PDFs
2. **Intelligent Extraction**: Identifies official GitHub repos and project pages
3. **Source Tracking**: Marks extracted URLs with source='ai_extraction'
4. **Validation**: Verifies URLs are accessible and valid
5. **Storage**: Saves to repositories and project_pages tables

### Source Types

Data comes from multiple sources, tracked in the `source` field:

- **`hf_api`**: Extracted from Hugging Face API (most reliable)
- **`ai_extraction`**: Extracted using AI from PDFs
- **`pwc_archive`**: From legacy PapersWithCode data dump
- **`manual`**: Manually added by users/admins

### URL Extraction Service

Located in `backend/genai_steps/`:

```bash
# Run URL extraction manually
uv run --env-file backend/keys.env python backend/genai_steps/extract_github_and_project_page_url.py

# Or use the hourly CRON job (recommended)
uv run --env-file backend/keys.env cron/hourly/extract_urls.py
```

**Features**:
- Memory-optimized for 4GB RAM
- Rate-limited to respect OpenRouter API limits (20 req/min)
- Processes 50 papers/hour continuously
- Skips papers already processed by HF API
- Handles PDF download failures gracefully

**API Configuration**:
Requires `PWC_OPENROUTER_API_KEY` in `backend/keys.env`:
```bash
PWC_OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Database & Data Sources

### PostgreSQL Database Schema

The database (`paperswithcode_hf`) uses PostgreSQL with the following main tables:

**Core Tables**:
- **`papers`**: Papers with metadata, abstracts, ArXiv IDs, versions, citation counts
- **`authors`**: Authors with Hugging Face profile integration
- **`repositories`**: GitHub repositories with star counts and update timestamps
- **`project_pages`**: Project page URLs for papers
- **`tasks`**: AI/ML task hierarchy (Computer Vision → Object Detection → etc.)
- **`methods`**: Methods/techniques (ResNet, Transformer, Adam, etc.)
- **`datasets`**: Benchmark datasets (COCO, ImageNet, etc.)
- **`evaluations`**: Benchmark results with metrics and ranks
- **`metrics`**: Evaluation metrics (AP, WER, BLEU, etc.)
- **`areas`**: Research areas (Computer Vision, NLP, etc.)

**Junction Tables** (many-to-many):
- **`paper_authors`**: Papers ↔ Authors
- **`paper_tasks`**: Papers ↔ Tasks
- **`paper_methods`**: Papers ↔ Methods
- **`paper_repositories`**: Papers ↔ Repositories
- **`paper_project_pages`**: Papers ↔ Project Pages
- **`dataset_tasks`**: Datasets ↔ Tasks

**Tracking Tables**:
- **`repository_star_history`**: Historical star count snapshots for trending

**Indexes**:
- Full-text search indexes on paper titles and abstracts (PostgreSQL GIN)
- B-tree indexes on frequently queried fields (ArXiv IDs, dates, etc.)

### Original Data Files

Located in `data/legacy_pwc_data/`:

1. **`papers-with-abstracts.json`** (2.2GB) - Complete papers database:
   - Paper metadata, abstracts, authors, proceedings
   - ArXiv IDs and URLs
   - Associated tasks, methods, datasets
   - GitHub repository links

2. **`evaluation-tables.json`** (236MB) - Benchmark evaluation data:
   - Task descriptions and hierarchies
   - Dataset information and leaderboards
   - Model performance metrics

3. **`jul-28-datasets.json`** - Dataset definitions
4. **`jul-28-methods.json`** - Method definitions
5. **`links-between-papers-and-code.json`** - Paper-repository associations

### Database Setup

```bash
# Create database
psql -U postgres -c "CREATE DATABASE paperswithcode_hf;"

# Set up schema
psql -U postgres -d paperswithcode_hf -f backend/database/papers_setup/setup_database.sql

# Import papers
uv run --env-file backend/keys.env python backend/database/papers_setup/add_hf_papers.py

# Import legacy PWC data (if needed)
uv run --env-file backend/keys.env python backend/database/papers_setup/add_pwc_papers_streaming.py
```

For detailed database setup, see `backend/database/README.md` and `docs/POSTGRESQL_GUIDE.md`.

## Development Guidelines

### Backend API Development

When adding new API endpoints, follow this workflow:

1. **Define Pydantic Models** (`backend/models/api.py`):
   ```python
   from pydantic import BaseModel

   class DatasetCreateRequest(BaseModel):
       name: str
       description: str
       url: str
       task_ids: list[int]
   ```

2. **Extend Database Models** (`backend/models/database.py`):
   ```python
   from sqlalchemy import Column, Integer, String

   class DBDataset(Base):
       __tablename__ = "datasets"
       id = Column(Integer, primary_key=True)
       name = Column(String, nullable=False)
   ```

3. **Create/Update Service** (`backend/services/`):
   ```python
   class DatasetService:
       def __init__(self, db: Session):
           self.db = db

       def create_dataset(self, request: DatasetCreateRequest):
           # Business logic here
           pass
   ```

4. **Add Router Endpoints** (`backend/routers/`):
   ```python
   from fastapi import APIRouter, Depends
   from backend.services.dataset_service import DatasetService

   router = APIRouter()

   @router.post("/datasets/")
   async def create_dataset(
       request: DatasetCreateRequest,
       db: Session = Depends(get_database_session)
   ):
       service = DatasetService(db)
       return service.create_dataset(request)
   ```

5. **Include Router in Main App** (`backend/main.py`):
   ```python
   from backend.routers import datasets

   app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
   ```

### Service Layer Pattern

**Always use the service layer** for business logic. Don't put complex logic in routers.

```python
# ✅ GOOD: Logic in service
# backend/services/paper_service.py
class PaperService:
    def get_trending_papers(self, limit: int = 20):
        # Complex query with star velocity calculations
        return self.db.query(...)

# backend/routers/papers.py
@router.get("/papers/trending")
async def get_trending(service: PaperService = Depends()):
    return service.get_trending_papers(limit=20)

# ❌ BAD: Logic in router
@router.get("/papers/trending")
async def get_trending(db: Session = Depends()):
    # Complex query directly in router
    return db.query(...)
```

### Database Connection Pattern

Use dependency injection for database sessions:

```python
from backend.database.connection import get_database_session
from sqlalchemy.orm import Session

@router.get("/papers/")
async def get_papers(db: Session = Depends(get_database_session)):
    # db is automatically managed (opened/closed)
    pass
```

For scripts, use context manager:

```python
from backend.database.connection import db_manager

with db_manager.session_local() as session:
    papers = session.query(DBPaper).limit(10).all()
```

### Frontend Development (TypeScript & React)

- **Location**: All frontend code in `frontend/` directory
- Use TypeScript strict mode with proper interfaces for all props
- Follow naming conventions: PascalCase for components, camelCase for hooks
- Import organization: React/external → UI components → custom components → hooks/utils
- Use TanStack Query for data fetching and caching
- Implement proper loading states and error boundaries

**API Client Pattern** (`frontend/src/lib/api.ts`):
```typescript
export async function searchPapers(query: string): Promise<Paper[]> {
  const response = await fetch(
    `http://localhost:8000/api/v1/papers/search?q=${query}`
  );
  return response.json();
}
```

**React Hook Pattern** (`frontend/src/hooks/usePapers.ts`):
```typescript
import { useQuery } from '@tanstack/react-query';
import { searchPapers } from '@/lib/api';

export function usePapers(query: string) {
  return useQuery({
    queryKey: ['papers', query],
    queryFn: () => searchPapers(query),
    staleTime: 5 * 60 * 1000,
  });
}
```

### UI & Styling

- Use shadcn/ui components from `frontend/src/components/ui/` (don't edit manually)
- Custom design system with paper-specific colors (blue, teal, purple, pink, orange, green)
- Responsive design with mobile-first approach
- Use `cn()` utility for conditional classes

### Python Development

- **Package Management**: Use `uv add package_name` to add dependencies (auto-updates pyproject.toml)
- **Environment**: All Python scripts run with `uv run --env-file backend/keys.env`
- **Code Style**: Follow PEP 8, use type hints, proper error handling
- **Logging**: Use proper logging (not print statements) for all scripts

### CRON Job Development

When creating new CRON jobs:

1. **Use the template** from `cron/README.md`
2. **Inherit from DatabaseCronJob** (`cron/utils/cron_helpers.py`)
3. **Implement proper logging** with timestamps and statistics
4. **Add to manage_cron.py** for monitoring
5. **Test manually** before scheduling

```python
from cron.utils.cron_helpers import DatabaseCronJob

class MyCronJob(DatabaseCronJob):
    def __init__(self):
        super().__init__(
            job_name="my_job",
            log_level="INFO"
        )

    def run(self):
        self.logger.info("Starting job")
        # Job logic here
        self.logger.info("Completed successfully")

if __name__ == "__main__":
    job = MyCronJob()
    success = job.execute()
    sys.exit(0 if success else 1)
```

## Code Quality Requirements

### Before Committing

**Frontend**:
1. **ALWAYS run `npm run lint`** in `frontend/` directory - Fix all ESLint errors
2. Check TypeScript compilation errors
3. Test key functionality works
4. Verify responsive design

**Backend**:
1. Test API endpoints with curl or in browser at `/docs`
2. Run relevant tests: `uv run --env-file backend/keys.env python backend/tests/test_*.py`
3. Verify Python scripts run without errors
4. Check that database operations work correctly

**CRON Jobs**:
1. Test manually: `uv run --env-file backend/keys.env cron/manage_cron.py test <job_name>`
2. Check logs for errors: `tail cron/logs/*.log`
3. Verify database updates occurred

### Testing Patterns

**API Testing**:
```bash
# Test endpoint exists
curl "http://localhost:8000/api/v1/papers/recent"

# Test with parameters
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"

# Test POST endpoint
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "description": "Test dataset", "url": "https://test.com", "task_ids": [1]}'
```

**Python Testing**:
```bash
# Run specific test
uv run --env-file backend/keys.env python backend/tests/test_authors_api.py

# Test CRON job
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations
```

## Special Considerations

### Route Management

- All new routes must be added ABOVE the catch-all `*` route in `frontend/src/App.tsx`
- Use React Router v6 patterns for navigation

### API Rate Limits

**GitHub API**:
- Authenticated: 5,000 requests/hour
- Strategy: 0.8s delays (90% utilization)
- Token required: PWC_GITHUB_TOKEN

**Semantic Scholar API**:
- Limit: 1 request/second
- Strategy: 1.3s delays (conservative)
- Token required: PWC_SEMANTIC_SCHOLAR_API_KEY

**OpenRouter API** (for URL extraction):
- Paid tier: 1,000 requests/day, 20 requests/minute
- Strategy: 50 papers/hour with buffer
- Token required: PWC_OPENROUTER_API_KEY

### Memory Constraints

The VPS has only 4GB of RAM. Scripts are optimized:
- Batch processing with small batch sizes
- Streaming JSON parsing (ijson library)
- Database query limiting
- Memory-efficient data structures

### Performance Optimization

- Use database indexes for frequently queried fields
- Implement pagination for large result sets
- Use TanStack Query caching on frontend
- Batch database operations
- Use CRON jobs for expensive operations (don't run synchronously in API)

## Documentation

For more detailed information, see:

**Backend/API**:
- `backend/README.md` - Backend setup and development
- `docs/API_GUIDE_ADDING_DATA.md` - Quick reference for adding data via API
- `docs/ADDING_EVALUATIONS_GUIDE.md` - Detailed evaluation management
- `docs/API_EXPANSION_PLAN.md` - Complete API roadmap
- `docs/AUTHORS_API_IMPLEMENTATION.md` - Authors API details

**Database**:
- `backend/database/README.md` - Database setup guide
- `docs/POSTGRESQL_GUIDE.md` - PostgreSQL connection and security
- `docs/DATABASE_SCHEMA_UML.md` - Database schema visualization

**CRON Jobs**:
- `cron/README.md` - Comprehensive CRON documentation
- `docs/TRENDING_API.md` - Trending papers feature

**Frontend**:
- `docs/FRONTEND_TRENDING_UPDATE.md` - Frontend trending integration
- `docs/LATEX_RENDERING.md` - LaTeX math rendering

## Quick Reference

### Common Tasks

**Start development**:
```bash
# Terminal 1: Backend
uv run --env-file backend/keys.env backend/run_server.py

# Terminal 2: Frontend
cd frontend && npm run dev
```

**Add a new dataset**:
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{"name": "MyDataset", "description": "Description", "url": "https://...", "task_ids": [1]}'
```

**Add an evaluation result**:
```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{"paper_id": 123, "task_id": 1, "dataset_id": 5, "metrics": {"AP": "45.0"}}'
```

**Check CRON status**:
```bash
uv run --env-file backend/keys.env cron/manage_cron.py summary
```

**View API documentation**:
```
http://localhost:8000/docs
```

### Environment Variables

All in `backend/keys.env`:
```bash
# Database
PWC_DB_USER=paperswithcode_user
PWC_DB_PASSWORD=your_password
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode_hf

# API Keys
PWC_GITHUB_TOKEN=ghp_your_token
PWC_SEMANTIC_SCHOLAR_API_KEY=your_key
PWC_HF_TOKEN=hf_your_token
PWC_OPENROUTER_API_KEY=sk-or-v1-your_key
```

### Key Paths

- Backend API: `http://localhost:8000/api/v1/`
- Frontend: `http://localhost:5173/`
- API Docs: `http://localhost:8000/docs`
- Database: `backend/database/`
- CRON Jobs: `cron/`
- Services: `backend/services/`
- Routers: `backend/routers/`
- Documentation: `docs/`
