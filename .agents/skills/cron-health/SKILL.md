---
name: cron-health
description: Investigate and report the health of the paperswithcode GitHub Actions CRON jobs (update_github_stars, update_citations, extract_urls, calculate_trending_scores, import_hf_daily_papers, preload_thumbnails, mirror_thumbnails_to_disk, link_methods_by_references). Use this skill whenever the user mentions cron health, cron status, scheduled jobs, broken cron, GitHub Actions runs, stale stars/citations/papers, missing recent papers, missing method tags on new papers, or asks variations like "are the cron jobs working?" / "did the github stars cron run today?" / "why are stars not updating?" — even when not phrased as a health check. Also use immediately whenever the user mentions updating any secret consumed by a cron (e.g. `PWC_GITHUB_TOKEN`, `PWC_OPENROUTER_API_KEY`, `PWC_GEMINI_API_KEY`, `PWC_HF_TOKEN`, `PWC_SEMANTIC_SCHOLAR_API_KEY`), because that is the single most common moment for these jobs to silently break.
---

# CRON job health check

This skill investigates whether the paperswithcode GitHub Actions CRON jobs are actually working, and produces a per-job health report. The goal is to catch silent failures — jobs that look fine in GitHub Actions but aren't producing useful work — not just to glance at green checkmarks.

## Architecture you must internalize before checking anything

Each `.github/workflows/cron-*.yml` workflow does exactly one thing: it SSH-es into the VPS and runs a wrapper script under `/root/python_projects/paperswithcode/.github/workflows/scripts/`, which in turn invokes the actual Python job via `uv run --env-file backend/keys.env`. So:

- The **schedule** lives in the workflow yml on GitHub.
- The **environment** (tokens, DB creds) is loaded **on the VPS** from `backend/keys.env` at the moment the wrapper script starts. Updating `keys.env` does **not** affect a process that is already running; you have to wait for the next invocation.
- **Logs** live in two places: GitHub Actions captures the SSH command's stdout, and some Python jobs additionally write timestamped files into `.github/workflows/scripts/logs/{name}_YYYYMMDD.log` via the `DatabaseCronJob` helper. Not every job writes a local log — `update_github_stars` in particular logs only via `print()` to stdout, so its local logs folder is sparse / nonexistent even when it's running fine.
- The **ground truth** for whether work happened is the **database state** (e.g. a row in `repository_star_history` whose `snapshot_at` is recent), not the existence of a log file.

This is why a single source of evidence is never enough. You must triangulate: workflow yml + local logs + database freshness + currently-running processes.

The current set of CRONs (read these files directly to confirm schedule and target script):

| Workflow | Schedule (UTC) | What it does | Where to verify it ran |
| --- | --- | --- | --- |
| `cron-update-github-stars.yml` | `0 * * * *` (hourly) | Fetches GitHub stars, snapshots history | `repository_star_history.snapshot_at` |
| `cron-update-citations.yml` | `30 * * * *` (hourly) | Updates citation counts via Semantic Scholar | local log `update_citations_hourly_*.log`; `papers.citation_count_updated_at` |
| `cron-extract-urls.yml` | `45 * * * *` (hourly) | Extracts GitHub/project URLs from PDFs via Gemini | local log `extract_urls_hourly_*.log`; `papers.urls_extracted` |
| `cron-calculate-trending-scores.yml` | `15 * * * *` (hourly) | Recomputes trending scores from star history | local log `calculate_trending_scores_*.log`; `repositories.trending_score_updated_at` |
| `cron-import-hf-daily-papers.yml` | `0 3 * * 2-6` (Tue–Sat 03:00) | Imports the previous day's HF daily papers | local log `import_hf_daily_papers_*.log`; new rows in `papers` |
| `cron-preload-thumbnails.yml` | `0 */3 * * *` (every 3h), `0 4 * * *` (daily 04:00), `30 4 * * *` (daily 04:30) | Three priority modes feeding the same script: every-3h trending preload, daily task-top-50 preload, daily newest-30-days broad preload. Also accepts `priority=missing-all` via workflow_dispatch for chunked long-tail backfills. | local log `preload_thumbnails_*.log` |
| `cron-mirror-thumbnails-to-disk.yml` | `0 5 * * *` (daily 05:00) | Mirrors the HF thumbnail bucket prefix to the VPS local cache served by `/api/thumbnails/{filename}` | local log `mirror_thumbnails_to_disk_*.log`; file count under `PWC_THUMBNAIL_TEMP_CACHE_DIR` should approach bucket file count |
| `cron-link-methods-by-references.yml` | `0 4 * * 0` (Sun 04:00) | Tags new papers with methods by walking each paper's bibliography and matching against `methods.source_paper_id` via Semantic Scholar | local log `link_methods_by_references_weekly_*.log`; `papers.methods_scanned_at` should be set for newly imported papers; new rows in `paper_methods` |

If a workflow file appears that you don't recognize, treat it as in-scope and figure out what it does — don't silently skip it.

## The investigation

Run this top-down. Start broad, then drill into anything suspicious. Many of the steps below can be run in parallel — batch tool calls aggressively.

### 1. Inventory the workflows

List `.github/workflows/cron-*.yml` and read each one to confirm its schedule and which wrapper / module it invokes on the VPS. The mapping above can drift; trust the file, not the table.

### 2. Try GitHub Actions first, but expect it to fail

Try `gh run list --workflow <file> --limit 10` and `gh run view <id>` for any failed runs. This is the cleanest signal when it works. It will often fail in this repo because:

- The `gh` CLI on the VPS is not authenticated (`gh auth login` was never run interactively).
- Even when authenticated via `GH_TOKEN`, the only token available — `PWC_GITHUB_TOKEN` from `keys.env` — belongs to a personal account that does not have access to the `huggingface/paperswithcode` repo's Actions API and returns HTTP 404 on `repos/huggingface/paperswithcode`. Don't waste cycles trying to coerce it.

If `gh` is unavailable, say so once and move on to the VPS-side evidence below. Don't apologize about it repeatedly.

### 3. Check VPS-side evidence in parallel

For every cron, gather three things in one batch of tool calls:

1. **Recent local logs**: `ls -la .github/workflows/scripts/logs/ | grep <prefix>` and `tail -40` on the most recent file (also peek at yesterday's if today's is short or missing).
2. **Currently-running processes**: `ps -ef | grep -E "(update_github_stars|update_citations|extract_urls|calculate_trending|import_hf|preload_thumbnails|mirror_thumbnails|link_methods_by_references)" | grep -v grep`. A long-running process here is normal during its window; a process that has been running for hours past its expected runtime is a stuck job.
3. **Lock files**: `ls /tmp/*.lock 2>/dev/null` — `github_stars.lock`, `trending_scores.lock`, etc. A stale lock from a killed run will block all subsequent invocations.

### 4. Verify the actual work landed in the database

This is the step that catches silent corruption that step 3 misses. For each job, check the freshness of what it's supposed to be writing:

```bash
# Stars (most common silent-failure suspect)
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf -t -c \
  "SELECT max(snapshot_at), count(*) FROM repository_star_history WHERE snapshot_at > now() - interval '6 hours';"

# Citations
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf -t -c \
  "SELECT max(citation_count_updated_at), count(*) FROM papers WHERE citation_count_updated_at > now() - interval '6 hours';"

# URLs extracted
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf -t -c \
  "SELECT max(updated_at), count(*) FROM papers WHERE urls_extracted = true AND updated_at > now() - interval '24 hours';"

# HF daily papers import
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf -t -c \
  "SELECT max(created_at), count(*) FROM papers WHERE created_at > now() - interval '36 hours';"
```

A "the workflow ran today" log line plus "the latest DB row is from 2 days ago" is the loudest possible signal that something is wrong. Always reconcile the two before declaring health.

For the database connection details, see `docs/database.md`. The credentials in the example above match the repo defaults; if they don't work, read the file.

### 5. If a token was just changed, prove it actually works

The single most common failure mode is an expired or revoked secret. Whenever the user has updated a token (or a job's been silently broken for >24h), test the new token end-to-end with the exact auth header the script uses, not just whatever `gh` is happy with:

```bash
TOKEN="$(grep ^PWC_GITHUB_TOKEN backend/keys.env | cut -d= -f2)"
curl -s -o /dev/null -w "HTTP %{http_code}  remaining=%header{x-ratelimit-remaining}\n" \
  -H "Authorization: token $TOKEN" \
  -H "User-Agent: PapersWithCode-Stars/1.0" \
  https://api.github.com/repos/huggingface/transformers
# Pick a *previously-failing* repo from the logs and test it too — some 401s are repo-specific (e.g. SAML SSO).
```

Equivalents:
- `PWC_OPENROUTER_API_KEY`: `curl -H "Authorization: Bearer $KEY" https://openrouter.ai/api/v1/auth/key`
- `PWC_GEMINI_API_KEY`: send a tiny request to `generativelanguage.googleapis.com/v1beta/models?key=$KEY`
- `PWC_HF_TOKEN`: `curl -H "Authorization: Bearer $KEY" https://huggingface.co/api/whoami-v2`
- `PWC_SEMANTIC_SCHOLAR_API_KEY`: `curl -H "x-api-key: $KEY" "https://api.semanticscholar.org/graph/v1/paper/10.18653/v1/N18-3011"`

The script in `update_github_stars.py:163` uses `Authorization: token …`; reproduce that exact format. A 200 from `gh` doesn't necessarily mean a 200 from the script.

### 6. The "stale env in a running process" trap

When `keys.env` is edited to fix a credential, a job that is **already running** at that moment is stuck with the **old** value, because env vars are loaded once at process start. This is doubly dangerous for `update_github_stars` because on a `None` API response it calls `mark_repository_group_as_processed(...)` (`update_github_stars.py:425-430`), which advances `last_updated` for the group — so a token-broken run silently burns the freshness window of every recent repo, and the next (good-token) run will skip them until that window expires (1h for recent, 7d for regular).

Detect this trap with:

```bash
stat -c '%y' backend/keys.env
ps -eo pid,lstart,cmd | grep -E "(update_github_stars|update_citations|extract_urls|calculate_trending|import_hf|preload_thumbnails|mirror_thumbnails|link_methods_by_references)" | grep -v grep
```

If any process's `lstart` is **older** than `keys.env`'s mtime, it's running with stale credentials. Confirm with strace + a brief packet capture if needed:

```bash
timeout 4 strace -p <pid> -e trace=write -s 200 2>&1 | grep -E "(API error|401|403|rate limit)"
```

If you see auth errors from a stale-env process, kill it cleanly so the next scheduled invocation picks up the new env, and clear the lock file:

```bash
kill <pid> ...      # kill the wrapper, uv shim, and python child
rm -f /tmp/<lock>.lock
```

Don't `kill -9` unless `kill` doesn't work after a few seconds — give it a chance to close its DB session.

### 7. Sanity check: is the schedule even firing?

If a job's local log and DB freshness are *both* stale and there's no running process, the workflow itself may not be firing. Compare the workflow's cron schedule to the local log filenames (date suffix) over the past few days. Repeated missing dates point at a GitHub Actions side problem (paused workflow, secret missing, SSH key rotated, GitHub-wide outage of scheduled runs). Note that GitHub silently disables scheduled workflows in repos with no recent activity — if the repo has been quiet, the schedule may have been suspended and need a manual `workflow_dispatch` to re-arm.

## Reporting format

Output a per-job table with **Job · Schedule · Status · Last completed · Notes**, then a separate "Issues found" section with concrete severity. Don't list everything as ✅ if a single source of evidence said so — escalate to ⚠️ when log says success but DB freshness disagrees.

Severity rubric:

- **🔴 broken**: not producing work in the DB for ≥ one full schedule cycle, OR auth errors in current run, OR stuck process past its `max_runtime`.
- **⚠️ degraded**: workflow runs but with elevated error/warning rate, OR DB freshness within one cycle but slipping.
- **✅ healthy**: producing fresh work in the DB within the expected cycle.
- **❓ unknown**: no signal in any of the three sources (rare; always investigate further before reporting).

Always include, for each broken job, a one-line "what's needed to fix" — even if it's "wait for the next scheduled run" or "rotate the X token".

## Things to avoid

- Don't declare success based only on green checkmarks in `gh run list`. The workflow exiting 0 only proves SSH worked, not that the script did anything useful.
- Don't run a long job (`update_github_stars` runs ~55 minutes) just to "test" it — verify with `curl` against the actual API instead.
- Don't `kill -9` a running cron without `kill` first; the script needs to close its DB session.
- Don't edit `keys.env` and then assume currently-running jobs picked up the change. They didn't.
- Don't over-trust `manage_cron.py summary` in isolation — its `Active: 0` is correct (the VPS uses GitHub Actions, not local crontab) and its status detection only sees jobs that write local logs, missing `update_github_stars` entirely.
