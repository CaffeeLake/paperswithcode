# Repository layout

Directory tree and frontend entrypoints for navigating the codebase.

## Project tree

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
├── .github/workflows/scripts/ # Automated CRON job scripts
│   ├── README.md             # Comprehensive CRON documentation
│   ├── hourly/               # High-performance hourly jobs (RECOMMENDED)
│   │   ├── update_github_stars.py      # 4,500 repos/hour
│   │   ├── update_citations.py         # 2,800 papers/hour
│   │   ├── extract_urls.py             # 50 papers/hour (AI-powered)
│   │   └── calculate_trending_scores.py
│   ├── daily/                # Legacy daily jobs
│   │   └── import_hf_daily_papers.py   # Import HF papers (hourly)
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
├── docs/                      # Documentation
├── scripts/                   # Utility scripts
│   ├── export_tasks_to_csv.py
│   └── import_tasks_from_csv.py
├── pyproject.toml            # Python dependencies managed by uv
├── uv.lock                   # Lockfile for Python dependencies
├── start_services.sh         # Start backend + frontend
└── stop_services.sh          # Stop backend + frontend
```

## Frontend core structure

- **Entry Point**: `frontend/src/main.tsx` → `frontend/src/App.tsx` (routing setup)
- **Routing**: React Router v6 with routes defined in `frontend/src/App.tsx`
- **State Management**: TanStack Query for server state, React hooks for local state
- **Styling**: Tailwind CSS with custom design system and shadcn/ui components
- **API Client**: `frontend/src/lib/api.ts` — uses `fetch` to call the backend

See also `docs/frontend.md` for UI features and conventions.
