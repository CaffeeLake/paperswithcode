# PapersWithCode documentation

Keep documentation short and tied to a workflow. The code, FastAPI `/docs`, and
the database schema are the source of truth for implementation details.

## Living guides

- `development-guide.md` — conventions and local checks.
- `data-workflows.md` — datasets, evaluations, metrics, and task hierarchy.
- `database.md` — database access and security.
- `deployment.md` — production networking and release checks.
- `operations.md` — cron, monitoring, and admin review.
- `keyword-matching.md` — keyword behavior and bulk relinking.
- `DATABASE_SCHEMA_UML.md` — current schema reference.

The root `README.md` covers setup. `AGENTS.md` contains the short contributor
quickstart. Cron-specific implementation details live beside the cron scripts in
`.github/workflows/scripts/README.md`.

## Writing Guidelines

- Prefer code and tests over explanatory prose.
- Keep only instructions that are not obvious from the code or command help.
- Keep examples executable (`uv run --env-file backend/keys.env …`, `npm run …`).
- Link to the owning code path instead of duplicating its implementation.

## Quick Links

- API docs (local): `http://localhost:8000/docs`
- Frontend dev server: `http://localhost:5173`
- Production: `https://paperswithcode.co`
