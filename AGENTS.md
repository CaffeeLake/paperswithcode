# AGENTS.md

Guidance for AI agents working in this repository.

## Essentials

- Do not add `SUMMARY.md` files; implement changes directly.
- Avoid heavy `try`/`except`; keep logic readable.
- Use background tasks in Cursor for long-running work unless you are actively debugging.
- **Run Python with** `uv run --env-file backend/keys.env …` (venv + env vars).
- Prefer `DBPaper.is_latest_version` over `== True`; use `~DBPaper.urls_extracted` instead of `== False`.
- Database access: **`docs/database.md`**.
- **Hardware**: Hetzner VPS, ~4GB RAM / 80GB disk — many scripts assume low RAM.
- Start/stop app stack: `./start_services.sh` / `./stop_services.sh`.
- API base path: **`http://localhost:8000/api/v1/`** (interactive docs: `/docs`).

## Project overview

Paperswithcode.ai: **React** frontend + **FastAPI** backend + **PostgreSQL**. Data from [Hugging Face papers](https://huggingface.co/papers) plus the legacy PapersWithCode dumps under `data/legacy_pwc_data/`. **CRON** jobs (`cron/`) import HF papers, refresh stars and citations, compute trending, and extract URLs with GenAI.

**Stack**: React 18, TS, Vite, shadcn/ui, Tailwind, TanStack Query, React Router v6 • FastAPI, SQLAlchemy • PostgreSQL + full-text search • Nginx + Let’s Encrypt in production • `uv` (Python), `npm` (frontend).

**Production**: `https://paperswithcode.co` — see **`docs/deployment.md`**.

## Essential commands

### Backend (repo root)

```bash
uv run --env-file backend/keys.env backend/run_server.py
# or: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

curl "http://localhost:8000/api/v1/papers/recent?limit=5"
curl "http://localhost:8000/api/v1/papers/search?q=transformer"
```

### Frontend (`frontend/`)

```bash
npm run dev
npm run build
npm run lint    # before commit
```

### Database (examples)

```bash
uv add some_package
uv sync
psql -U postgres -d paperswithcode_hf -f backend/database/papers_setup/setup_database.sql
uv run --env-file backend/keys.env python backend/database/papers_setup/add_hf_papers.py
uv run --env-file backend/keys.env python backend/tests/test_authors_api.py
```

### CRON

```bash
uv run --env-file backend/keys.env cron/manage_cron.py summary
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations
```

## Where to read more

| Topic | Document |
|--------|-----------|
| Repo tree, `frontend/` layout | `docs/repository-layout.md` |
| Endpoint tables & curl samples | `docs/rest-api-catalog.md` |
| Router summary, adding endpoints | `docs/backend-api.md` |
| Datasets & evaluations via API | `docs/data-workflows.md` |
| CRON detail, GitHub Actions, GenAI URLs | `docs/automation-reference.md` |
| Dashboard, trending, PDF checks | `docs/operations.md` |
| Tables & legacy JSON dumps | `docs/schema-and-data-files.md` |
| Dev patterns, testing, limits | `docs/development-guide.md` |
| DB connection & security | `docs/database.md` |
| Deploy, DNS, HTTPS | `docs/deployment.md` |
| UI features | `docs/frontend.md` |
| Keyword APIs | `docs/keyword-matching.md` |
| Schema diagram | `docs/DATABASE_SCHEMA_UML.md` |
| Cron implementation notes | `cron/README.md`, `backend/database/README.md` |

## Quick reference

**Local URLs**: API `http://localhost:8000/api/v1/` • Vite devoften `http://localhost:5173/` • API docs `http://localhost:8000/docs`

**Common tasks**

```bash
# Dev servers
uv run --env-file backend/keys.env backend/run_server.py
cd frontend && npm run dev

uv run --env-file backend/keys.env cron/manage_cron.py summary
```

**`backend/keys.env` (names only)** — `PWC_DB_*`, `PWC_GITHUB_TOKEN`, `PWC_SEMANTIC_SCHOLAR_API_KEY`, `PWC_HF_TOKEN`, `PWC_OPENROUTER_API_KEY`

**Key paths**: `backend/services/` • `backend/routers/` • `backend/database/` • `cron/` • `docs/`
