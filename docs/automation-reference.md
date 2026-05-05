# Automation reference (CRON detail, GitHub Actions, GenAI URLs)

See **`docs/operations.md`** for the operational overview, dashboard, and trending pipeline. This page expands schedules, production triggers, and URL extraction.

## Hourly jobs (`cron/hourly/`)

Recommended for production; more efficient than legacy daily batches.

### 1. Update GitHub Stars (`update_github_stars.py`)

- **Typical schedule**: every hour
- **Performance**: on the order of thousands of repositories per hour (rate-limited)
- **Scope**: repositories due for refresh (e.g. ~7-day cadence per repo)
- **Features**: GitHub rate-limit aware delays, deduplication by owner/name
- **Command**: `uv run --env-file backend/keys.env cron/hourly/update_github_stars.py`

### 2. Update Citations (`update_citations.py`)

- **Typical schedule**: hourly (often offset from stars)
- **Scope**: papers with ArXiv IDs
- **Features**: Semantic Scholar rate limiting; updates counts and `citation_updated_at`
- **Command**: `uv run --env-file backend/keys.env cron/hourly/update_citations.py`

### 3. Extract URLs (`extract_urls.py`)

- **Typical schedule**: hourly
- **Scope**: recent papers missing extracted URLs
- **Features**: OpenRouter (e.g. Gemini) on PDFs; sets `urls_extracted`; `source='ai_extraction'`; tuned for low RAM
- **Requires**: `PWC_OPENROUTER_API_KEY` in `backend/keys.env`
- **Command**: `uv run --env-file backend/keys.env cron/hourly/extract_urls.py`

### 4. Trending scores (`calculate_trending_scores.py`)

- **Typical schedule**: hourly
- **Scope**: recent papers/repos
- **Features**: star velocity, `repository_star_history`, feeds `/api/v1/papers/trending`
- **Command**: `uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py`

## Daily jobs (`cron/daily/`)

### Import Hugging Face daily papers (`import_hf_daily_papers.py`)

- **Schedule**: early morning UTC, Tue–Sat (HF paper weekdays)
- **Purpose**: import curated HF submissions into papers, authors, repositories, project pages
- **Command**: `uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py`

## Management CLI

```bash
uv run --env-file backend/keys.env cron/manage_cron.py summary
uv run --env-file backend/keys.env cron/manage_cron.py list
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations
uv run --env-file backend/keys.env cron/manage_cron.py status import_hf_daily_papers
uv run --env-file backend/keys.env cron/manage_cron.py cleanup
tail -f cron/logs/update_github_stars_$(date +%Y%m%d).log
```

## GitHub Actions → VPS

Workflows live under `.github/workflows/cron-*.yml`. Each run SSHs to the Hetzner host and invokes the shell wrappers or Python entrypoints; scripts still read `backend/keys.env` on the server.

| Workflow | Schedule (UTC) | Runs on VPS |
|----------|----------------|-------------|
| `cron-import-hf-daily-papers.yml` | `0 3 * * 2-6` | `cron/daily/import_hf_daily_papers.py` |
| `cron-update-github-stars.yml` | `0 * * * *` | `cron/run_github_stars.sh` |
| `cron-calculate-trending-scores.yml` | `30 * * * *` | `cron/run_trending_scores.sh` |
| `cron-update-citations.yml` | `30 * * * *` | `cron/run_citations_hourly.sh` |
| `cron-extract-urls.yml` | `45 * * * *` | `cron/run_extract_urls_hourly.sh` |

**Repository secrets**: `VPS_HOST`, `VPS_USER`, `VPS_SSH_PRIVATE_KEY` (ed25519 private key whose public key is in `~/.ssh/authorized_keys` on the VPS).

Manual runs: Actions tab → workflow → **Run workflow**.

## GenAI: URL extraction

Process:

1. PDF fetch and validation (see `docs/operations.md`, PDF validation section)
2. Model analyzes PDF for official GitHub and project URLs
3. Persist to `repositories` / `project_pages` with appropriate `source`

**Source values** (`source` column):

- **`hf_api`**: from Hugging Face API
- **`ai_extraction`**: from GenAI PDF pass
- **`pwc_archive`**: legacy PapersWithCode dump
- **`manual`**: human-entered

**Manual run** (same logic as hourly job, outside CRON):

```bash
uv run --env-file backend/keys.env python backend/genai_steps/extract_github_and_project_page_url.py
```

`backend/keys.env`:

```bash
PWC_OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Further reading: `cron/README.md`, `backend/genai_steps/`.
