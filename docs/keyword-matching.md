# Keyword Matching & Management

## Shared Matching Module

- Location: `backend/utils/keyword_matching.py`
- Two strategies:
  - `find_matching_items_simple` – used for tasks; returns *all* matches.
  - `find_matching_items_longest_match` – used for methods; prevents overlapping/shorter matches (e.g., `GPT` vs `GPT-4`).
- Case handling:
  - Keywords containing uppercase letters → substring match (captures `LLMs`, `OpenCLIP`, `VLMs`).
  - All-lowercase keywords → word-boundary regex (`\b…\b`) to avoid accidental matches (e.g., `transformer` vs `transformed`).

## Where It’s Used

| File | Strategy | Purpose |
| --- | --- | --- |
| `cron/daily/import_hf_daily_papers.py` | simple + longest | Auto-tag new Hugging Face papers with tasks/methods. |
| `backend/database/tasks_setup/link_papers_by_task_keywords.py` | simple | Retag entire corpus for task coverage. |
| `backend/database/methods_setup/link_papers_by_keywords.py` | longest | Retag corpus for methods while honoring hierarchical names. |

The consolidation replaced dozens of one-off scripts—refer to `backend/database/{tasks_setup,methods_setup}/archive/` for historical imports.

### Running Bulk Linking

```bash
uv run --env-file backend/keys.env backend/database/tasks_setup/link_papers_by_task_keywords.py
uv run --env-file backend/keys.env backend/database/methods_setup/link_papers_by_keywords.py
```

Expect ~0.86 task tags and ~2.4 method tags per paper after the improved strategy (statistics from October 2025).

## Keywords API

Both tasks and methods expose keyword management endpoints:

```
POST   /api/v1/tasks/{task_id}/keywords
DELETE /api/v1/tasks/{task_id}/keywords
PUT    /api/v1/tasks/{task_id}/keywords

POST   /api/v1/methods/{method_id}/keywords
DELETE /api/v1/methods/{method_id}/keywords
PUT    /api/v1/methods/{method_id}/keywords
```

Example:

```bash
curl -X POST http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["function-calling", "tool-use"]}'
```

Implementation details:
- Keywords stored as comma-separated strings on the `keywords` column of `tasks` and `methods` tables.
- API resolves targets by numeric ID, slug, or (for methods) name.
- Service layer trims whitespace, enforces uniqueness (case-insensitive), and supports full replacement via PUT.

## Maintenance Tips

- When adding new keywords, keep the casing rule in mind: lowercase for phrases, uppercase for acronyms/initialisms.
- Re-run bulk linking after changing keyword sets to backfill historical data.
- Monitor new acronyms (e.g., `LVLM`, `MCP`) and add them to method keywords promptly to maintain coverage.
- Archive unused manual scripts to `backend/database/*/archive/` to avoid future confusion.

## Future Ideas

- Keyword synonym tables (e.g., map `LLM` → `large language model`).
- Confidence scores or flags for ambiguous matches.
- Admin UI for reviewing suggested tags before promotion.

_Last updated: 7 November 2025_
