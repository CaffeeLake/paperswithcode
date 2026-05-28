# Backend API Overview

The FastAPI application (`backend/main.py`) exposes REST endpoints under `/api/v1/`.  Each router delegates to a service layer in `backend/services/` so that business logic stays out of the HTTP layer.

## Router Summary (November 2025)

| Router | Path | Highlights |
| --- | --- | --- |
| `papers.py` | `/papers` | Full-text search, trending feed, versioned ArXiv access, stats. |
| `datasets.py` | `/datasets` | List/create datasets, dataset→task associations, evaluation lookup. |
| `evaluations.py` | `/evaluations` | CRUD for benchmark results, rank recalculation, metric validation. |
| `tasks.py` | `/tasks` | Task hierarchy, parents/children, keyword management, task→papers feed. |
| `methods.py` | `/methods` | Method search, papers per method, keyword management. |
| `areas.py` | `/areas` | Research areas and task listings. |
| `authors.py` | `/authors` | Author catalog with Hugging Face metadata and paper lists. |
| `repositories.py` | `/repositories` | GitHub repositories, star counts, paper associations. |
| `metrics.py` | `/metrics` | Metric catalog (direction, descriptions). |
| `cron.py` | `/cron` | Job status, detailed history, health endpoint for dashboard. |
| `thumbnails.py` | `/thumbnails` | Serves cached paper thumbnails. |
| `bookmarks.py` | `/me/bookmarks`, `/me/saved` | Per-HF-user bookmark CRUD; `pwc_session` cookie required. |
| `pending_edits.py` | `/me/paper-edits`, `/admin/paper-edits` | Non-admin paper edit submissions (`require_user`) and admin review queue / approve / reject (`require_admin`). See `docs/operations.md` for the SQL + admin-API review workflow. |

### Service-Layer Pattern

- Each router injects a SQLAlchemy session via `get_database_session`.
- Services (e.g., `DatasetService`, `EvaluationService`) own business rules, validation, and error handling.
- Shared exceptions live in `backend/utils/exceptions.py` and are translated to HTTP responses in routers.

### Pagination & Filtering

- All list endpoints accept `page`/`page_size` query parameters (default `page_size=50`, capped at `100`).
- Text search parameters (`q`, `search`) are case-insensitive.
- Sorting uses `ordering` or `order_by` query parameters with optional `-` prefix for descending order.

## Adding New Endpoints

1. Define Pydantic models in `backend/models/api.py`.
2. Add/extend SQLAlchemy models in `backend/models/database.py` if needed.
3. Implement service methods in `backend/services/<domain>_service.py`.
4. Expose routes in `backend/routers/<domain>.py` with dependency-injected services.
5. Register the router in `backend/main.py` with prefix `/api/v1`.
6. Document the workflow in the relevant Markdown guide (`data-workflows.md`, etc.).

## Testing & Tooling

```bash
# Run focused test modules
uv run --env-file backend/keys.env python backend/tests/test_authors_api.py
uv run --env-file backend/keys.env python backend/tests/test_rank_recalculation.py

# Ad-hoc endpoint checks
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"
curl "http://localhost:8000/api/v1/tasks/?area_id=1&page_size=20"
```

When modifying routers/services, add or update tests in `backend/tests/` and keep FastAPI docs (`/docs`) clean.

## Roadmap Snapshot

- ✅ Authors, Areas, Tasks, Methods, Datasets, Evaluations, Trending & Cron endpoints shipped.
- 🚧 Cross-entity helper endpoints (e.g., `/papers/{id}/repositories`) remain planned.
- 🧭 Keep new routes versioned under `/api/v1/`; break changes require `/api/v2/` planning.

_Last updated: 7 November 2025_
