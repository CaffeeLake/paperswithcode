# PapersWithCode Documentation

This folder contains the working documentation for the recreated PapersWithCode stack.  The goal of the refresh is to keep a small set of living documents that match the codebase as it exists today (November 2025).

## How To Navigate

- `backend-api.md` – current FastAPI surface area, routers, and service conventions.
- `rest-api-catalog.md` – per-router endpoint tables and example `curl` calls.
- `data-workflows.md` – dataset + evaluation ingestion, metric rules, and validation tooling.
- `database.md` – connection details, security posture, and day‑to‑day SQL operations.
- `schema-and-data-files.md` – high-level table list, legacy dumps, initial import commands.
- `deployment.md` – server topology, DNS/HTTPS setup, and runtime verification.
- `frontend.md` – major UI features (task leaderboards, admin editing, LaTeX titles, trending view).
- `keyword-matching.md` – shared keyword matching module and keyword management API.
- `operations.md` – CRON jobs, monitoring dashboard, trending pipeline, and PDF validation.
- `automation-reference.md` – CRON detail, GitHub Actions triggers, GenAI URL extraction.
- `repository-layout.md` – full repo tree and frontend entrypoints.
- `development-guide.md` – backend/frontend patterns, testing, rate limits, RAM notes.
- `DATABASE_SCHEMA_UML.md` – authoritative schema dump for quick reference.

Repository root **`AGENTS.md`** is a short index; deeper material lives in the files above.

## Writing Guidelines

- Prefer updating an existing topic doc (or `AGENTS.md`’s table of links) over adding unrelated new files.
- Keep examples executable (`uv run --env-file backend/keys.env …`, `npm run …`, etc.).
- Cross-link code paths using backticks (e.g., `backend/services/evaluation_service.py`).
- Record dates when process-sensitive instructions change.

## Quick Links

- API docs (live): `http://localhost:8000/docs`
- Frontend dev server: `http://localhost:8080`
- Production domain (after DNS/SSL): `https://paperswithcode.co`

For an at-a-glance view of the platform, read `deployment.md` first, then `operations.md`.
