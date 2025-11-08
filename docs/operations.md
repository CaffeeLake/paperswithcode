# Operations & Automation

## Cron Job Overview

All jobs live in `cron/` and are executed with `uv run --env-file backend/keys.env …`.

| Schedule | Script | Purpose |
| --- | --- | --- |
| `0 * * * *` | `cron/hourly/update_github_stars.py` | Refresh star counts for official repositories (batch size tuned for rate limits). |
| `15 * * * *` | `cron/hourly/calculate_trending_scores.py` | Compute EMA-based trending scores using repository star history. |
| `30 * * * *` | `cron/hourly/update_citations.py` | Pull citation counts from Semantic Scholar for ArXiv papers. |
| `45 * * * *` | `cron/hourly/extract_urls.py` | AI-assisted GitHub/project URL extraction for papers lacking resources. |
| `0 3 * * 2-6` | `cron/daily/import_hf_daily_papers.py` | Import curated Hugging Face submissions (Tue–Sat). |

Useful commands:

```bash
uv run --env-file backend/keys.env cron/manage_cron.py summary
uv run --env-file backend/keys.env cron/manage_cron.py status update_github_stars
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations
uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

## Cron Dashboard

- Route: `/cron-dashboard` on the frontend (linked from the site header).
- Backend endpoints: `/api/v1/cron/status`, `/api/v1/cron/job/{name}`, `/api/v1/cron/health`.
- Auto-refresh every 30 seconds (toggleable), color-coded job states, next-run predictions, duration parsing for both “Runtime: … minutes” and “Duration: … seconds” logs.
- Pulls data from log files in `cron/logs/` and merges with crontab discovery.

Use the dashboard to ensure health score stays ≥80%.  For command-line visibility, rely on `cron/manage_cron.py`.

## Trending Pipeline

1. `update_github_stars.py` snapshots star counts into `repository_star_history`.
2. `calculate_trending_scores.py` computes a trending score per repository using an exponential moving average (α = 0.15) of hourly velocity.
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

## Troubleshooting Checklist

| Issue | Resolution |
| --- | --- |
| Trending endpoint empty | Verify GitHub stars job is running and trending scores have at least two snapshots; check `repositories.trending_score_updated_at`. |
| Cron dashboard shows “Unknown” | Ensure log file exists (`cron/logs/<job>_YYYYMMDD.log`) and job is scheduled in crontab. |
| AI URL extraction stalls | Inspect `cron/logs/extract_urls_*.log` for CAPTCHA hits; consider slowing batch size or updating API key in `backend/keys.env`. |
| Cron logs filling disk | Run `uv run --env-file backend/keys.env cron/manage_cron.py cleanup`; default policy keeps 30 days. |

_Last updated: 7 November 2025_
