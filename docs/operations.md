# Operations & Automation

## Cron Job Overview

Job implementations live in `.github/workflows/scripts/`, but production never
executes them from a checkout. GitHub Actions invokes the installed
`pwc-cron` launcher, which pins execution to `production/current`, runs as
`pwc-cron`, enforces an allowlist and timeout, and records release provenance.

| Schedule | Script | Purpose |
| --- | --- | --- |
| Every minute (local systemd timer) | `.github/workflows/scripts/hourly/process_curation_thumbnails.py` | Claim remote-curation thumbnail requests and record terminal results as `pwc-cron`. |
| Manual dispatch only | `.github/workflows/scripts/hourly/update_hot_github_trending.py` | Staging-ready hot pipeline; production schedule remains intentionally disabled. |
| `0 * * * *` | `.github/workflows/scripts/hourly/update_github_stars.py` | Refresh fresh and weekly official repositories concurrently using separate GitHub accounts. |
| `15 * * * *` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` | Compute EMA-based trending scores using repository star history. |
| `30 * * * *` | `.github/workflows/scripts/hourly/update_citations.py` | Pull citation counts from Semantic Scholar for ArXiv papers. |
| `45 * * * *` | `.github/workflows/scripts/hourly/extract_urls.py` | AI-assisted GitHub/project URL extraction for papers lacking resources. |
| `0 * * * *` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` | Import the current day's Hugging Face submissions not yet in the DB (hourly). |
| `5 * * * *` | `.github/workflows/scripts/hourly/sync_3d_arena.py` | Refresh paper-linked Elo results from the living 3D Arena leaderboard. |
| `15 * * * *` | `.github/workflows/scripts/hourly/sync_open_asr.py` | Refresh paper-linked WER and RTFx results from the living Open ASR Leaderboard. |
| `20 2 * * *` | `.github/workflows/scripts/daily/sync_hf_organizations.py` | Reconcile the strict featured HF organization manifest and append new paper links. |
| `40 3 * * *` | `.github/workflows/scripts/daily/calculate_organization_trending_scores.py` | Snapshot organization momentum and refresh rolling 30-day ranks. |
| `30 4 * * *` | `.github/workflows/scripts/daily/preload_thumbnails.py` | Generate and upload missing paper thumbnails to the HF bucket. |
| `0 5 * * *` | `.github/workflows/scripts/daily/mirror_thumbnails_to_disk.py` | Mirror the entire thumbnail bucket prefix down to the VPS local cache so `/api/thumbnails/{filename}` always serves from local disk. |

Useful production commands:

```bash
sudo pwc-cron status
pwc cron health
pwc cron health refresh_paper_embeddings --strict --json
journalctl -u 'run-u*.service' --since today
```

Remote paper-curation thumbnail requests run through the local
`pwc-curation-thumbnails.timer` and the allowlisted
`process_curation_thumbnails` command. Inspect the timer with
`systemctl status pwc-curation-thumbnails.timer`; retry existing terminal
failures once with:

```bash
sudo pwc-cron process_curation_thumbnails --retry-failed
```

## Admin Dashboard

- Route: `/admin-dashboard` on the frontend (linked from the admin user menu). The old `/cron-dashboard` URL redirects here.
- Backend endpoints: `/api/v1/cron/status`, `/api/v1/cron/job/{name}`, `/api/v1/cron/health`.
- Codex add-evals/enrich controls and their remote-job queue are intentionally
  disabled during the environment migration. Staging cannot mutate the shared
  catalog and production does not expose the retired write-capable sidecar.
- Auto-refreshes CRON health every 30 seconds (toggleable).
- Pulls production CRON health from
  `/var/lib/paperswithcode/production/cron-logs`.

Use the dashboard to ensure health score stays ≥80%. For command-line
visibility, use `pwc cron health` and `pwc-cron status`.

Deployed scheduled jobs run through `sudo /usr/local/sbin/pwc-cron <job>` from
the immutable `production/current` release. Use `pwc cron health`, `pwc-status`,
and journald for diagnostics; do not execute scheduled scripts from the
developer checkout. CRON logs live in
`/var/lib/paperswithcode/production/cron-logs` and are retained for 30 days.

Environment deployment, rollback, nginx, backup, and release layout are
documented in [deployment.md](deployment.md).

Blue/green deployments record every pointer mutation in
`environments/<environment>/activation-journal.json`. If `pwc-status` reports
`live-with-old-slot-draining`, do not restart or kill the old service; run
`sudo pwc-reap <environment>` later. It stops a slot only after both chat and
gateway stream counts are zero and then removes only unreferenced releases and
runtimes. A journal phase ending in `smoke-pending` or
`automatic-rollback-in-progress` is an incident requiring pointer and public
smoke inspection before another deployment.

## Trending Pipeline

Once production activation is separately authorized, queue ownership is
exclusive: the 15-minute hot job owns latest papers aged
0–30 days (500 calls/run), the hourly fresh queue owns days 31–180 (2,500
calls/run), and the weekly queue owns older repositories (1,000 calls/run).
The 30-day ownership boundary is intentionally fixed across selection and
health checks; it is not an environment override.
`PWC_GITHUB_TOKEN_HOT` is optional in
`/etc/paperswithcode/production-cron.env`; when absent, hot requests use
`PWC_GITHUB_TOKEN` and preserve a 500-call reserve.

1. `update_hot_github_trending.py` is the targeted path that snapshots hot repositories, calculates their
   EMA scores, and updates only their linked latest papers in the same run.
2. `update_github_stars.py` snapshots the fresh and weekly queues into
   `repository_star_history`.
3. The hourly `calculate_trending_scores.py` and
   `calculate_paper_trending_scores.py` jobs reconcile the full populations.
   Targeted paper writes still normalize against the full live GitHub/HF corpus.
4. Database views and `/api/v1/papers/trending` expose the resulting scores.

```bash
curl "http://localhost:8000/api/v1/papers/trending?limit=10&max_age_days=180"
```

Response snippet:

```json
{
  "paper_id": "51998",
  "arxiv_id": "2507.15061",
  "title": "WebShaper: Agentically Data Synthesizing…",
  "date_published": "2025-07-20",
  "repository": {
    "url": "https://github.com/Alibaba-NLP/WebWalker",
    "owner": "Alibaba-NLP",
    "name": "WebWalker",
    "num_stars": 15549
  },
  "trending": {
    "velocity_24h": 2.143,
    "trending_score": 0.326,
    "stars_gained_24h": 66
  }
}
```

Frontend integration (`frontend/src/pages/Papers.tsx`) uses the dedicated endpoint when users select the 🔥 Trending tab without a search query, and gracefully falls back to `/papers` plus sort options for mixed queries.

The checked-in workflow is `workflow_dispatch`-only. A merge to `main` or a
staging deployment does not activate production, and the installed
`/usr/local/sbin/pwc-cron` will not recognize this command until deploy tooling
from the authorized production SHA is installed.

Production activation requires a separately authorized and reviewed sequence:

1. Install the checked-in deploy tooling from the exact authorized production SHA.
2. Deploy that same SHA to production so the immutable release contains the job.
3. Verify `sudo pwc-cron status` lists `update_hot_github_trending`.
4. In a separate reviewed commit, add the `*/15 * * * *` schedule to
   `cron-update-hot-github-trending.yml`.

After those steps, recovery and selection-only checks are:

```bash
pwc cron health update_hot_github_trending --strict --json
sudo pwc-cron update_hot_github_trending --dry-run
```

The dry run prints the bounded selected population and projected shared-token
calls without GitHub requests or database writes. Disable the schedule to roll
back; snapshots are retained. If it stays disabled, restore hot papers to the
hourly fresh ownership before releasing that rollback.

The hourly paper reconciliation also supports temporary, linearly decaying
emergency floors. Configure comma-separated `identifier:decay_hours` entries in
the production CRON overlay (hours default to 72):

```dotenv
PWC_TRENDING_PIN_ARXIV_IDS=2606.16140:72
PWC_TRENDING_PIN_PAPER_IDS=104054:72
```

The paper-ID form supports external papers without an arXiv ID. Both forms
share the persisted pin state and decay behavior. The CRON worker stores that
state in its writable lock directory so immutable releases remain read-only.
Use pins only as a bridge while the underlying ranking signal is corrected.

## PDF Validation for URL Extraction

- Helper: `_is_valid_pdf` in `backend/utils/pdf_utils.py`
- Ensures downloaded files start with `%PDF-`, contain `%%EOF`, exceed 1 KB, and are not HTML/reCAPTCHA placeholders.
- Critical errors (rate limiting, CAPTCHA) are surfaced so papers are retried later instead of being marked as processed.
- Unit tests: `tests/test_pdf_validation.py`, integration tests: `tests/test_pdf_download_integration.py`.

## Thumbnail Storage

The browser always loads paper previews through `/api/thumbnails/{filename}`.
Production can store generated JPEGs in a private Hugging Face Storage Bucket by
setting:

```bash
PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket
PWC_THUMBNAIL_HF_BUCKET_ID=huggingface/pwc-thumbnail
PWC_THUMBNAIL_HF_BUCKET_PREFIX=thumbnails
PWC_HF_TOKEN=<token with bucket access>
```

Use a dry run before uploading the current VPS cache:

```bash
uv run --env-file backend/keys.env scripts/sync_thumbnails_to_hf_bucket.py --create-bucket
uv run --env-file backend/keys.env scripts/sync_thumbnails_to_hf_bucket.py --create-bucket --apply
```

After spot-checking `/api/thumbnails/...`, the old `thumbnails/` directory can be
removed from the VPS because the bucket is the durable copy. The backend keeps a
small `PWC_THUMBNAIL_TEMP_CACHE_DIR` for recently served bucket objects.

### Local disk mirror

The thumbnail bucket is **private**, so the browser cannot fetch images directly
from `huggingface.co/buckets/...`; every `<img src="/api/thumbnails/...">`
request has to go through FastAPI. To keep that fast, the daily
`mirror_thumbnails_to_disk` cron runs `huggingface_hub.sync_bucket` to
incrementally pull the entire bucket prefix into `PWC_THUMBNAIL_TEMP_CACHE_DIR`
on the VPS. Once the mirror finishes, `ThumbnailService` finds every requested
file on local disk and never has to do a per-request HF download. To run it
manually (e.g. for first-time bootstrap):

```bash
sudo pwc-cron mirror_thumbnails_to_disk
```

## Troubleshooting Checklist

| Issue | Resolution |
| --- | --- |
| Trending endpoint empty | Verify GitHub stars job is running and trending scores have at least two snapshots; check `repositories.trending_score_updated_at`. |
| Cron dashboard shows “Unknown” | Run `pwc-cron status`, inspect `/var/lib/paperswithcode/production/cron-logs`, and check the matching GitHub Actions run. |
| AI URL extraction stalls | Inspect production CRON health and the matching immutable-release job logs; do not rerun it from the checkout. |
| Pending edits not landing in DB | Confirm the submitter is signed in (HF session cookie); the `POST /api/v1/me/paper-edits` endpoint requires `require_user`. Then run `SELECT * FROM pending_paper_edits WHERE status='pending' ORDER BY created_at DESC LIMIT 10;` to inspect recent submissions. |

## Pending Paper Edits Review

Non-admin Hugging Face users submit edits to the paper-page surfaces (tasks,
methods, evaluations, GitHub repositories, project pages) through
`POST /api/v1/me/paper-edits`. The submission lands in the
`pending_paper_edits` table with `status = 'pending'`; live data does not
change until an admin approves it. Admin direct edits via the existing
`/papers/{id}/...` and `/evaluations/...` admin endpoints still bypass this
queue. The frontend admin queue UI is intentionally deferred — review and
approval happens through SQL plus the admin API.

### List pending submissions

Run this against the production DB to surface the current review queue:

```sql
SELECT id,
       paper_id,
       hf_username,
       is_author,
       edit_type,
       created_at,
       jsonb_pretty(proposed_payload) AS proposed_payload,
       jsonb_pretty(current_payload)  AS current_payload
FROM pending_paper_edits
WHERE status = 'pending'
ORDER BY created_at DESC;
```

For a quick triage view:

```sql
SELECT id, paper_id, hf_username, is_author, edit_type, created_at
FROM pending_paper_edits
WHERE status = 'pending'
ORDER BY created_at DESC;
```

You can also ask the agent to surface pending edits — it will run the same
query and summarize the diff between `current_payload` and `proposed_payload`
for you.

### Approve or reject via the admin API

Both endpoints require the HF admin cookie (sign in via the site) or the
`X-Admin-Token` header. Approval re-uses the same backend mutation services
that admin direct edits call, so a future "auto-approve author edits" hook can
reuse the exact same code path. Reject simply records the row as rejected with
an optional note; it does not touch live data.

```bash
# Approve
curl -X POST \
    -H "X-Admin-Token: $PWC_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"admin_note": "looks correct"}' \
    https://paperswithcode.co/api/v1/admin/paper-edits/{edit_id}/approve

# Reject
curl -X POST \
    -H "X-Admin-Token: $PWC_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"admin_note": "task tag was incorrect"}' \
    https://paperswithcode.co/api/v1/admin/paper-edits/{edit_id}/reject
```

`GET /api/v1/admin/paper-edits` lists rows server-side (status / paper_id /
edit_type filters supported) and `GET /api/v1/admin/paper-edits/{id}` returns
a single row including both payloads.

Approved/rejected rows stay in the table for auditing; the same SQL query
with `status = 'approved'` or `status = 'rejected'` shows historical
decisions along with `reviewed_by` and `reviewed_at`.

### Payload shapes

Each `proposed_payload` matches the underlying admin mutation endpoint:

- `tasks` &rarr; `{"task_ids": [int, ...]}`
- `methods` &rarr; `{"method_ids": [int, ...]}`
- `repositories` &rarr; `{"repositories": [{"url": str, "is_official": bool}, ...]}`
- `project_pages` &rarr; `{"project_pages": [{"url": str, "is_official": bool}, ...]}`
- `evaluations` &rarr; `{"operations": [{"op": "create" | "update" | "delete", ...}, ...]}`
  - `create` &rarr; `{ "op": "create", "data": { task_id, dataset_id, metrics, best_metric, ... } }`
  - `update` &rarr; `{ "op": "update", "evaluation_id": int, "data": { ... } }`
  - `delete` &rarr; `{ "op": "delete", "evaluation_id": int }`
| Cron logs filling disk | Verify `systemd-tmpfiles` policy; production CRON logs are bounded to 30 days. Use `pwc-status` to include disk usage in the audit. |

_Last updated: 7 November 2025_
## Durable chat sessions (staging)

Chat content is private user data. PostgreSQL is the live source of truth;
opaque Agent SDK transcripts are stored separately from the sanitized UI
projection. Never print message content or transcript JSON in operational
checks. User-confirmed deletion removes live rows immediately; verified
disaster-recovery backups expire under the normal 30-day remote rotation and
are not a product undo mechanism.

Before enabling durable chat, confirm the backup target reports `"private":
true` and is organization-owned. The daily backup service receives its
organization-authorized bucket credential only through
`production-cron.env`; neither application identity can read that overlay. The
target is selected with `PWC_POSTGRES_BACKUP_BUCKET`.

Content-free storage checks:

```bash
df -h /
sudo -u postgres psql -d paperswithcode_hf -c "
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname LIKE 'chat_%'
ORDER BY pg_total_relation_size(relid) DESC;"
sudo -u postgres psql -d paperswithcode_hf -c "
SELECT count(*) AS sessions,
       sum(message_count) AS messages,
       pg_size_pretty(avg(transcript_bytes + projection_bytes)::bigint)
         AS average_logical_bytes
FROM chat_sessions;"
```

Treat filesystem use at or above 85%, any `transcript_status='degraded'`, or a
recovery-spool entry as an alert. The recovery spool is private, bounded by
`PWC_CHAT_RECOVERY_SPOOL_MAX_SESSIONS`, and exists only to reconcile SDK mirror
failures; it is not a second session store.
