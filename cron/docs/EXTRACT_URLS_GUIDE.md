# URL Extraction Cron Guide

`cron/hourly/extract_urls.py` finds official GitHub repositories and project
pages for papers that still have `urls_extracted = false`.

## Production Schedule

Production runs through GitHub Actions:

```text
cron-extract-urls.yml -> 45 * * * * -> cron/run_extract_urls_hourly.sh
```

The wrapper runs on the VPS from `/root/python_projects/paperswithcode` and uses
`backend/keys.env`.

## Requirements

`backend/keys.env` must include:

```bash
PWC_GEMINI_API_KEY=your-gemini-key-here
```

The job validates the Gemini key before processing papers.

## Manual Runs

```bash
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env cron/hourly/extract_urls.py
./cron/run_extract_urls_hourly.sh
```

Logs are written to:

```text
cron/logs/extract_urls_hourly_YYYYMMDD.log
cron/logs/extract_urls_wrapper_YYYYMMDD.log
```

## Current Runtime Settings

The job is tuned for the Gemini free tier and the 4 GB VPS:

```python
self.papers_per_hour = 14
self.batch_size = 10
self.start_year = 2014
self.use_paid_tier = False
```

Increase `papers_per_hour` only after confirming the Gemini quota and the VPS
memory headroom.

## Processing Rules

The job selects recent-enough ArXiv papers with abstracts where
`urls_extracted = false`. It downloads/analyzes the paper, saves official
GitHub/project URLs, and marks successfully processed papers as extracted.

Rate limits, invalid API keys, and PDF failures are treated as retryable; those
papers remain eligible for a later run.

## Troubleshooting

```bash
uv run --env-file backend/keys.env cron/manage_cron.py status extract_urls_hourly
tail -f cron/logs/extract_urls_hourly_$(date +%Y%m%d).log
tail -f cron/logs/extract_urls_wrapper_$(date +%Y%m%d).log
```

Common checks:

- Confirm `PWC_GEMINI_API_KEY` is present on the VPS, not just locally.
- Run the wrapper manually to verify `backend/keys.env` is found.
- Check GitHub Actions for SSH or wrapper failures.
- Check Gemini quota if logs show rate-limit failures.
