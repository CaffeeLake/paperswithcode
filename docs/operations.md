# Operations & Automation

## Cron Job Overview

All jobs live in `.github/workflows/scripts/` and are executed with `uv run --env-file backend/keys.env …`.

| Schedule | Script | Purpose |
| --- | --- | --- |
| `0 * * * *` | `.github/workflows/scripts/hourly/update_github_stars.py` | Refresh star counts for official repositories (batch size tuned for rate limits). |
| `15 * * * *` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` | Compute EMA-based trending scores using repository star history. |
| `30 * * * *` | `.github/workflows/scripts/hourly/update_citations.py` | Pull citation counts from Semantic Scholar for ArXiv papers. |
| `45 * * * *` | `.github/workflows/scripts/hourly/extract_urls.py` | AI-assisted GitHub/project URL extraction for papers lacking resources. |
| `0 3 * * 2-6` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` | Import curated Hugging Face submissions (Tue–Sat). |
| `30 4 * * *` | `.github/workflows/scripts/daily/preload_thumbnails.py` | Generate and upload missing paper thumbnails to the HF bucket. |
| `0 5 * * *` | `.github/workflows/scripts/daily/mirror_thumbnails_to_disk.py` | Mirror the entire thumbnail bucket prefix down to the VPS local cache so `/api/thumbnails/{filename}` always serves from local disk. |

Useful commands:

```bash
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py summary
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py status update_github_stars
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py test update_citations
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py cleanup
```

## Cron Dashboard

- Route: `/cron-dashboard` on the frontend (linked from the site header).
- Backend endpoints: `/api/v1/cron/status`, `/api/v1/cron/job/{name}`, `/api/v1/cron/health`.
- Auto-refresh every 30 seconds (toggleable), color-coded job states, next-run predictions, duration parsing for both “Runtime: … minutes” and “Duration: … seconds” logs.
- Pulls data from log files in `.github/workflows/scripts/logs/` and merges with crontab discovery.

Use the dashboard to ensure health score stays ≥80%.  For command-line visibility, rely on `.github/workflows/scripts/manage_cron.py`.

## Trending Pipeline

1. `update_github_stars.py` snapshots star counts into `repository_star_history`.
2. `calculate_trending_scores.py` computes a trending score per repository using an exponential moving average (α = 0.75) of hourly velocity.
3. Database views (`trending_repositories_24h`, `trending_papers_24h`) join the latest official repositories to papers.
4. API endpoint `/api/v1/papers/trending` reads from the view and supports filters:

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
PWC_THUMBNAIL_HF_BUCKET_ID=<owner>/<bucket>
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
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env \
    python -m scripts.daily.mirror_thumbnails_to_disk
```

## Troubleshooting Checklist

| Issue | Resolution |
| --- | --- |
| Trending endpoint empty | Verify GitHub stars job is running and trending scores have at least two snapshots; check `repositories.trending_score_updated_at`. |
| Cron dashboard shows “Unknown” | Ensure log file exists (`.github/workflows/scripts/logs/<job>_YYYYMMDD.log`) and job is scheduled in crontab. |
| AI URL extraction stalls | Inspect `.github/workflows/scripts/logs/extract_urls_*.log` for CAPTCHA hits; consider slowing batch size or updating API key in `backend/keys.env`. |
| Cron logs filling disk | Run `uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py cleanup`; default policy keeps 30 days. |

_Last updated: 7 November 2025_
