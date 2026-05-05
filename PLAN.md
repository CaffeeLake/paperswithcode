---
name: github actions cron job fixes
overview: Plan to bring the GitHub Actions workflows for paperswithcode back to a green, monitorable state. Five cron-* workflows were created on 2026-05-05 11:02 UTC and are mostly working, but `cron-extract-urls` is failing on a Gemini API key error and three legacy workflows (`arxiv-sync.yml`, `test-database.yml`, `import-papers.yml`) reference deleted files from the previous database layer and have been failing for months.
---

# CRON Job Fix Plan

## Snapshot — 2026-05-05 ~13:50 UTC

All 8 workflows are `active` in the GitHub Actions UI. Status of the most recent run per workflow:

| Workflow | Schedule | Last run | Result |
|---|---|---|---|
| `cron-update-github-stars.yml` | hourly :00 | 13:12 | success |
| `cron-calculate-trending-scores.yml` | hourly :30 | 12:46 | success |
| `cron-update-citations.yml` | hourly :30 | 12:44 | in_progress (~70 min in, 90-min timeout) |
| `cron-extract-urls.yml` | hourly :45 | 12:51 | **failure** (Gemini API key invalid) |
| `cron-import-hf-daily-papers.yml` | Tue–Sat 03:00 | — | not yet due (workflow file created today) |
| `arxiv-sync.yml` | daily 06:00 | 07:56 | **failure** — and ≥35 prior daily failures |
| `test-database.yml` | push / PR / manual | 11:02 | **failure** — and every push since 2025-11-10 |
| `import-papers.yml` | manual only | never | n/a |

Cron workflow files (`.github/workflows/cron-*.yml`) were all created today, so we're inside the first hour of a new schedule. The three legacy workflows (`arxiv-sync.yml`, `test-database.yml`, `import-papers.yml`) predate the current architecture and have been broken silently.

---

## Tasks

### 1. Fix `cron-extract-urls` — Gemini API key on VPS

**Symptom** (run id 25377441723, 12:51 UTC):

```
An error occurred with model gemini-2.5-flash: 400 INVALID_ARGUMENT.
{'error': {'code': 400, 'message': 'API Key not found. Please pass a valid API key.',
 'status': 'INVALID_ARGUMENT', ... 'reason': 'API_KEY_INVALID', ...}}
An error occurred with model gemini-2.5-pro: 400 INVALID_ARGUMENT. ... API_KEY_INVALID ...
##[error]Process completed with exit code 1.
```

**Root cause**: The workflow `ssh`es into the VPS and runs `cron/run_extract_urls_hourly.sh`, which calls `cron/hourly/extract_urls.py`. That script reads `PWC_GEMINI_API_KEY` via `backend.config.get_settings()` (see [`cron/hourly/extract_urls.py:76`](cron/hourly/extract_urls.py)). It validates the key on startup with `_validate_api_keys()` and, when validation fails, exits with `RuntimeError`. The local `backend/keys.env` in this repo has `PWC_GEMINI_API_KEY=AIzaSyDs4YMaEFtkAcMD8tzIfL6w8SO5QZtprtQ`, but the VPS's own `backend/keys.env` is what's actually consumed when the SSH command runs. That key is rejected by the Google Generative AI API.

**Fix**:
1. SSH into the VPS and inspect `~/python_projects/paperswithcode/backend/keys.env`.
2. Verify whether `PWC_GEMINI_API_KEY` exists and is valid (test against `https://generativelanguage.googleapis.com/v1beta/models?key=$KEY`).
3. Replace it with a valid key generated in [Google AI Studio](https://aistudio.google.com/apikey) under the same Google account paying for the existing quota.
4. Manually trigger the workflow (`gh workflow run cron-extract-urls.yml -R NielsRogge/paperswithcode`) and confirm the next run goes green.

**Note**: The `extract_urls.py` docstring still mentions OpenRouter (`backend.config.get_settings()` exposes both), but the actual code path uses `GoogleGenerator` directly with `PWC_GEMINI_API_KEY`. The misleading doc/AGENTS.md references to OpenRouter are documentation-only and can be cleaned up later — they are not the cause of the failure.

### 2. Bump timeout (and possibly chunk) `cron-update-citations`

**Symptom**: The 12:44 run is still going at 13:54 (≈70 min). Workflow timeout is `90` min; the next scheduled tick at 13:30 was already skipped because of `concurrency: cancel-in-progress: false`.

**Evidence**: VPS log `cron/logs/update_citations_hourly_20260505.log` shows the script actively updating papers and being throttled by Semantic Scholar at 13:54. So the job is healthy, just slow due to real API rate limits.

**Fix**:
1. Raise `timeout-minutes` in [`.github/workflows/cron-update-citations.yml`](.github/workflows/cron-update-citations.yml) from `90` → `180` (or `300`) so a single hourly run can finish even when Semantic Scholar throttles harder than usual.
2. Optionally cap papers per run inside `cron/hourly/update_citations.py` so the job is bounded to ≤ ~40 min of wall clock — this avoids GitHub Actions hours bloat and lets the next scheduled tick actually run instead of being skipped.
3. Consider moving the schedule off `:30` since `cron-calculate-trending-scores.yml` is also `:30`. Suggested: citations `:30`, trending `:15` — keeps both hourly without contending for the same VPS minute. (Both jobs SSH into the same box; not strictly a conflict, but operationally cleaner.)

### 3. Decide fate of legacy workflows: `arxiv-sync.yml`, `test-database.yml`, `import-papers.yml`

These three reference an obsolete database layer that no longer exists in the repo:

| Reference | Status |
|---|---|
| `backend/database/setup_database.sql` | moved → `backend/database/papers_setup/setup_database.sql` |
| `backend/database/db_connection.py` (`PapersDatabase`, `DatabaseConfig`) | replaced → `backend/database/connection.py` (different API) |
| `backend/database/arxiv_sync.py` | deleted |
| `backend/database/import_papers.py` | deleted |
| `backend/database/test_arxiv_sync.py` | deleted |

Failure log (run 25364592628, arxiv-sync, 07:56 UTC today):

```
psql: error: backend/database/setup_database.sql: No such file or directory
ModuleNotFoundError: No module named 'backend.database.db_connection'
##[error]Process completed with exit code 1.
```

`test-database.yml` fails identically on every push (since 2025-11-10).

**Decision needed**: Do these workflows still serve a purpose under the new architecture?

- **arxiv-sync.yml** — daily ArXiv fetch into a CI-only Postgres. The new pipeline imports papers from Hugging Face via `cron-import-hf-daily-papers.yml` against the production DB, not from ArXiv into a throwaway Postgres. → **Recommend delete.**
- **import-papers.yml** — manual one-shot import of `data/papers-with-abstracts.json` (the legacy PWC dump) into a CI Postgres. The production DB has been populated for months. → **Recommend delete.**
- **test-database.yml** — runs DB tests on push. There is no replacement test workflow today, so deleting it leaves zero CI for the database layer. → **Recommend rewrite** to use the current `backend.database.connection` module against a CI Postgres seeded from `backend/database/papers_setup/setup_database.sql`, or **delete** if we accept zero CI on database PRs.

**Action**:
1. Confirm with maintainer whether any of the three workflows are still needed.
2. For each one: either delete the YAML, or rewrite to point at the current paths/modules.
3. Whichever path we take, the failure-on-every-push behavior of `test-database.yml` should stop today — it adds noise to the Actions UI and lowers the signal of real failures.

### 4. Verify first run of `cron-import-hf-daily-papers`

The workflow file exists but has 0 historical runs because it was created today at 11:02 UTC, after the 03:00 UTC tick had already passed. First scheduled run: **Wed 2026-05-06 03:00 UTC**.

**Action**:
- Tomorrow morning, run `gh run list -R NielsRogge/paperswithcode -w cron-import-hf-daily-papers.yml -L 3` and confirm conclusion is `success`.
- If GitHub silently skips the cron (common in private repos with low activity), the fallback is to add a manual `gh workflow run cron-import-hf-daily-papers.yml -R NielsRogge/paperswithcode` to a daily reminder, or migrate the schedule to a self-hosted runner / VPS cron.

### 5. Address Node.js 20 deprecation warning

Every workflow run currently emits:

```
##[warning]Node.js 20 actions are deprecated. The following actions are running on
Node.js 20 and may not work as expected: actions/checkout@v4, actions/setup-python@v4,
actions/upload-artifact@v4, astral-sh/setup-uv@v3. Actions will be forced to run with
Node.js 24 by default starting June 2nd, 2026.
```

That deadline is **less than a month away**. After June 2nd, jobs will be force-migrated to Node 24, which can break older composite actions.

**Action** (one-shot bump across all workflows):
- `actions/checkout@v4` → `@v5` (Node 24)
- `actions/setup-python@v4` → `@v5`
- `actions/upload-artifact@v4` → `@v5`
- `astral-sh/setup-uv@v3` → `@v6`
- `webfactory/ssh-agent@v0.9.0` → check latest

Most relevant for `arxiv-sync.yml`, `test-database.yml`, `import-papers.yml` (they `checkout` and `setup-python`); the cron-* workflows only use `webfactory/ssh-agent` so are mostly fine.

### 6. Optional polish

- **Slack/Discord notifications on failure** — none of the current workflows notify on failure; we only notice when something downstream stops being updated. Consider adding `if: failure()` step that posts to a webhook for the cron-* jobs.
- **`.github/workflows/lint.yml`** — there is no CI for `npm run lint` in `frontend/` or for backend Python (ruff). Worth adding while we're cleaning up the Actions surface.

---

## Suggested execution order

1. (immediate, today) Fix Gemini key on VPS → unblock `cron-extract-urls`. Re-trigger and confirm green.
2. (today) Bump `cron-update-citations` timeout to 180 min, deconflict `:30` schedule with trending.
3. (this week) Decide delete vs rewrite for the three legacy workflows; ship whichever PR.
4. (tomorrow) Verify `cron-import-hf-daily-papers` 03:00 UTC run was successful.
5. (before June 2) Bump all action versions to Node 24-compatible majors.
6. (nice to have) Failure notifications + lint CI.
