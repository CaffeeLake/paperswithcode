# Automation reference (CRON detail, GitHub Actions, GenAI URLs)

See **`docs/operations.md`** for the operational overview, dashboard, and trending pipeline. This page expands schedules, production triggers, and URL extraction.

## Hourly jobs (`.github/workflows/scripts/hourly/`)

Recommended for production; more efficient than legacy daily batches.

### 1. Update GitHub Stars (`update_github_stars.py`)

- **Typical schedule**: every hour
- **Performance**: on the order of thousands of repositories per hour (rate-limited)
- **Scope**: repositories due for refresh (e.g. ~7-day cadence per repo)
- **Features**: GitHub rate-limit aware delays, deduplication by owner/name
- **Command**: `PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars`

### 2. Update Citations (`update_citations.py`)

- **Typical schedule**: hourly (often offset from stars)
- **Scope**: papers with ArXiv IDs
- **Features**: Semantic Scholar rate limiting; updates counts and `citation_updated_at`
- **Command**: `PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_citations`

### 3. Extract URLs (`url_extraction_agent`)

- **Typical schedule**: hourly
- **Scope**: newest HF imports, first-page home/task/method/conference papers, then the older backlog; all must be missing at least one official URL
- **Features**: one sandboxed Claude Agent SDK run per paper on Modal; native structured output; trusted VPS validation/persistence; `source='ai_extraction'`
- **Scale**: up to 100 papers/hour with at most 20 Modal containers
- **Requires**: GitHub Modal credentials and the existing Modal `anthropic` secret
- **Deploy**: `uv run modal deploy url_extraction_agent/modal_app.py`

### 4. Trending scores (`calculate_trending_scores.py`)

- **Typical schedule**: hourly
- **Scope**: recent papers/repos
- **Features**: star velocity, `repository_star_history`, feeds `/api/v1/papers/trending`
- **Command**: `PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores`

## Daily jobs (`.github/workflows/scripts/daily/`)

### Import Hugging Face daily papers (`import_hf_daily_papers.py`)

- **Schedule**: hourly (imports the current day's HF papers not yet in the DB)
- **Purpose**: import curated HF submissions into papers, authors, repositories, project pages
- **Command**: `PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.daily.import_hf_daily_papers`

## Management CLI

```bash
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py summary
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py list
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py test update_citations
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py status import_hf_daily_papers
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py cleanup
tail -f .github/workflows/scripts/logs/update_github_stars_$(date +%Y%m%d).log
```

## GitHub Actions → VPS

Workflows live under `.github/workflows/cron-*.yml`. Each run SSHs to the Hetzner host and invokes the shell wrappers or Python entrypoints; scripts still read `backend/keys.env` on the server.

| Workflow | Schedule (UTC) | Runs on VPS |
|----------|----------------|-------------|
| `cron-import-hf-daily-papers.yml` | `0 * * * *` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` |
| `cron-update-github-stars.yml` | `0 * * * *` | `.github/workflows/scripts/run_github_stars.sh` |
| `cron-calculate-trending-scores.yml` | `15 * * * *` | `.github/workflows/scripts/run_trending_scores.sh` |
| `cron-update-citations.yml` | `30 * * * *` | `.github/workflows/scripts/run_citations_hourly.sh` |
| `cron-extract-urls.yml` | `45 * * * *` | VPS select → Modal map → VPS persist |

**Repository secrets**: `VPS_HOST`, `VPS_USER`, `VPS_SSH_PRIVATE_KEY` (ed25519 private key whose public key is in `~/.ssh/authorized_keys` on the VPS), plus `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for URL extraction.

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
PWC_GEMINI_API_KEY=your-gemini-key-here
```

Further reading: `.github/workflows/scripts/README.md`, `backend/genai_steps/`.
