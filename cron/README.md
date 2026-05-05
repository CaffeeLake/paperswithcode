# PapersWithCode Cron Jobs

Production cron scheduling is driven by GitHub Actions. The workflows under
`.github/workflows/cron-*.yml` SSH into the VPS and run the entrypoints in this
directory with `uv run --env-file backend/keys.env ...`.

## Active Production Jobs

| Workflow | Schedule (UTC) | VPS entrypoint | Python job |
| --- | --- | --- | --- |
| `cron-update-github-stars.yml` | `0 * * * *` | `cron/run_github_stars.sh` | `cron/hourly/update_github_stars.py` |
| `cron-calculate-trending-scores.yml` | `15 * * * *` | `cron/run_trending_scores.sh` | `cron/hourly/calculate_trending_scores.py` |
| `cron-update-citations.yml` | `30 * * * *` | `cron/run_citations_hourly.sh` | `cron/hourly/update_citations.py` |
| `cron-extract-urls.yml` | `45 * * * *` | `cron/run_extract_urls_hourly.sh` | `cron/hourly/extract_urls.py` |
| `cron-import-hf-daily-papers.yml` | `0 3 * * 2-6` | direct `uv run` | `cron/daily/import_hf_daily_papers.py` |

The `test-database.yml` workflow is unrelated to cron scheduling.

## Directory Layout

```text
cron/
├── daily/
│   └── import_hf_daily_papers.py
├── hourly/
│   ├── calculate_trending_scores.py
│   ├── extract_urls.py
│   ├── update_citations.py
│   └── update_github_stars.py
├── backfill/
│   └── backfill_hf_papers.py
├── maintenance/
│   ├── cleanup_invalid_repositories.py
│   └── run_cleanup_invalid_repositories.sh
├── utils/
│   ├── cron_helpers.py
│   └── hf_paper_importer.py
├── manage_cron.py
└── run_*.sh
```

Generated logs are written to `cron/logs/`. Backfill checkpoint state is runtime
data and is intentionally ignored by git.

## Job Summary

`update_github_stars.py` refreshes repository star counts and writes historical
snapshots to `repository_star_history`. Recent papers are refreshed more often
than older papers so trending calculations have enough signal.

`calculate_trending_scores.py` computes EMA-smoothed trending scores from star
history and stores them on repositories for the trending API/view pipeline.

`update_citations.py` pulls citation counts from Semantic Scholar for ArXiv
papers. Runs are bounded so hourly Actions do not pile up under API throttling.

`extract_urls.py` uses Gemini to find official GitHub repositories and project
pages for papers that still have `urls_extracted = false`.

`import_hf_daily_papers.py` imports the previous weekday's Hugging Face papers
and auto-tags tasks/methods using keyword matching.

## Manual Utilities

The backfill and maintenance scripts are not scheduled by GitHub Actions:

```bash
uv run --env-file backend/keys.env cron/backfill/backfill_hf_papers.py
uv run --env-file backend/keys.env cron/backfill/backfill_hf_papers.py --max-papers 200

uv run --env-file backend/keys.env cron/maintenance/cleanup_invalid_repositories.py --dry-run
./cron/maintenance/run_cleanup_invalid_repositories.sh --limit 100
```

Keep these manual unless a production schedule is intentionally added.

## Management Commands

```bash
uv run --env-file backend/keys.env cron/manage_cron.py list
uv run --env-file backend/keys.env cron/manage_cron.py status
uv run --env-file backend/keys.env cron/manage_cron.py status update_citations_hourly
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations
uv run --env-file backend/keys.env cron/manage_cron.py summary
uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

The management script discovers `hourly/`, `daily/`, `weekly/`, and `monthly/`
Python jobs. It does not schedule jobs itself.

## Adding A Job

1. Put scheduled jobs under `cron/hourly/` or `cron/daily/`.
2. Reuse `DatabaseCronJob` from `cron/utils/cron_helpers.py` for DB-backed jobs.
3. Add or update a shell wrapper if the GitHub Action needs one.
4. Add a `.github/workflows/cron-*.yml` workflow if the job should run in production.
5. Run with `uv run --env-file backend/keys.env ...` before enabling a schedule.

## References

- GitHub Actions workflow overview: `.github/workflows/README.md`
- Operational overview: `docs/operations.md`
- Detailed automation notes: `docs/automation-reference.md`
- Trending implementation notes: `cron/hourly/README.md` and `cron/docs/TRENDING_EMA_GUIDE.md`
