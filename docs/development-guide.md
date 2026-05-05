# Development guide

Patterns for backend, frontend, CRON, testing, and production constraints.

## Backend: adding API endpoints

1. **Pydantic models** (`backend/models/api.py`):
   ```python
   from pydantic import BaseModel

   class DatasetCreateRequest(BaseModel):
       name: str
       description: str
       url: str
       task_ids: list[int]
   ```

2. **ORM models** (`backend/models/database.py`) when persistence changes:
   ```python
   from sqlalchemy import Column, Integer, String

   class DBDataset(Base):
       __tablename__ = "datasets"
       id = Column(Integer, primary_key=True)
       name = Column(String, nullable=False)
   ```

3. **Service** (`backend/services/`): implement business logic; keep routers thin.

4. **Router** (`backend/routers/`):
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

5. **Register** in `backend/main.py`:
   ```python
   from backend.routers import datasets
   app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
   ```

See also `docs/backend-api.md`.

## Service layer

Put business logic in services, not in routers.

```python
# Prefer: logic in service
class PaperService:
    def get_trending_papers(self, limit: int = 20):
        return self.db.query(...)

@router.get("/papers/trending")
async def get_trending(service: PaperService = Depends()):
    return service.get_trending_papers(limit=20)
```

## Database sessions

**API**: inject `get_database_session`.

```python
from backend.database.connection import get_database_session
from sqlalchemy.orm import Session

@router.get("/papers/")
async def get_papers(db: Session = Depends(get_database_session)):
    ...
```

**Scripts**: context manager.

```python
from backend.database.connection import db_manager

with db_manager.session_local() as session:
    papers = session.query(DBPaper).limit(10).all()
```

## Python service usage (scripts)

Prefer services over ad-hoc SQL when mutating domain data:

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
            task_ids=[9],
        )
        dataset = service.create_dataset(dataset_request)
        print(f"Created dataset: {dataset.slug}")
```

Dataset/evaluation HTTP examples: **`docs/data-workflows.md`**.

## Frontend (TypeScript & React)

- Code under `frontend/`; TypeScript strict; PascalCase components, camelCase hooks
- Imports: React/external → `components/ui` → custom components → hooks/utils
- Server state: TanStack Query; loading and error handling expected

**API client** (`frontend/src/lib/api.ts`):

```typescript
export async function searchPapers(query: string): Promise<Paper[]> {
  const response = await fetch(
    `http://localhost:8000/api/v1/papers/search?q=${query}`
  );
  return response.json();
}
```

**Hook** (`frontend/src/hooks/usePapers.ts`):

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

## UI & styling

- Use shadcn/ui from `frontend/src/components/ui/` (avoid hand-editing generated primitives)
- Tailwind + existing design tokens; responsive, mobile-first
- `cn()` for conditional classes

## Python conventions

- Dependencies: `uv add …`; run scripts with `uv run --env-file backend/keys.env …`
- PEP 8, type hints, logging instead of `print` in automation

## New CRON jobs

1. Follow `.github/workflows/scripts/README.md`
2. Subclass `DatabaseCronJob` in `.github/workflows/scripts/utils/cron_helpers.py`
3. Log with timestamps and summary stats
4. Register in `.github/workflows/scripts/manage_cron.py` where applicable
5. Test: `uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py test <job_name>`

```python
from scripts.utils.cron_helpers import DatabaseCronJob

class MyCronJob(DatabaseCronJob):
    def __init__(self):
        super().__init__(job_name="my_job", log_level="INFO")

    def run(self):
        self.logger.info("Starting job")
        # ...
        self.logger.info("Completed successfully")

if __name__ == "__main__":
    job = MyCronJob()
    success = job.execute()
    sys.exit(0 if success else 1)
```

## Before committing

**Frontend**: `npm run lint` in `frontend/`; fix TS/ESLint issues; smoke-test UI.

**Backend**: exercise `/docs` or `curl`; `uv run --env-file backend/keys.env python backend/tests/test_*.py` as relevant.

**CRON**: test via `manage_cron.py`; inspect `.github/workflows/scripts/logs/`.

## Testing examples

```bash
curl "http://localhost:8000/api/v1/papers/recent"
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "description": "Test dataset", "url": "https://test.com", "task_ids": [1]}'

uv run --env-file backend/keys.env python backend/tests/test_authors_api.py
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py test update_citations
```

## Routing (frontend)

- Register new routes **above** the catch-all `*` route in `frontend/src/App.tsx`
- React Router v6 patterns elsewhere

## API rate limits

- **GitHub**: authenticated budget ~5k/hour; jobs use conservative delays (`PWC_GITHUB_TOKEN`)
- **Semantic Scholar**: ~1 req/s practical limit (`PWC_SEMANTIC_SCHOLAR_API_KEY`)
- **OpenRouter** (URL extraction): respect daily/minute tiers (`PWC_OPENROUTER_API_KEY`)

## Memory and performance

- VPS baseline ~4GB RAM: prefer small batches, streaming JSON where applicable, limited queries
- Index hot columns; paginate large lists; cache on the client with TanStack Query
- Heavy work belongs in CRON, not request/response paths

## HTTPS, Nginx, production

DNS, TLS, Nginx, and troubleshooting: **`docs/deployment.md`**. Do not duplicate ops runbooks here.
