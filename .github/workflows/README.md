# GitHub Actions Workflows

This directory contains GitHub Actions workflows for running production cron jobs on the VPS, smoke-testing the current database layer, and deploying the Hugging Face Space mirror.

## Workflows

### Cron workflows (`cron-*.yml`)

**Purpose**: Trigger the active production maintenance jobs over SSH on the VPS.

**Schedules**:
- `cron-update-github-stars.yml`: hourly at `:00`
- `cron-calculate-trending-scores.yml`: hourly at `:15`
- `cron-update-citations.yml`: hourly at `:30`
- `cron-extract-urls.yml`: hourly at `:45`
- `cron-import-hf-daily-papers.yml`: Tue-Sat at 03:00 UTC

**What they do**:
- Load the VPS SSH key from GitHub Actions secrets.
- Add the VPS host key to `known_hosts`.
- Run the corresponding script from `/root/python_projects/paperswithcode` on the VPS.

### Test Database System (`test-database.yml`)

**Purpose**: Test database functionality on code changes.

**Triggers**:
- Push to main/develop branches (when database files change)
- Pull requests to main branch
- Manual trigger

**What it does**:
- Starts a clean PostgreSQL service.
- Uses `backend.database.connection` and SQLAlchemy models to create/drop tables.
- Inserts and queries a sample `Paper` row.

### Deploy Hugging Face Space (`deploy-hf-space.yml`)

**Purpose**: Build the static frontend mirror and upload it to the Hugging Face Space.

**Triggers**:
- Push to `main` when frontend, deploy script, or dependency lock files change
- Manual trigger with optional Space id and API URL inputs

**What it does**:
- Installs Python and frontend dependencies.
- Runs `.github/workflows/scripts/deploy_hf_space.py` with `--skip-restore` because CI is not serving `frontend/dist` through nginx.
- Uploads the generated static bundle to the Space using the `HF_TOKEN` repository secret.

## Database Configuration

Database code reads `PWC_`-prefixed environment variables:
- `PWC_DB_HOST`: Database host (localhost in CI)
- `PWC_DB_PORT`: Database port (5432)
- `PWC_DB_NAME`: Database name (`paperswithcode_hf` in CI)
- `PWC_DB_USER`: Database user (postgres in CI)
- `PWC_DB_PASSWORD`: Database password (postgres in CI)

## Production Setup

For production deployment, you'll need to:

1. **Set up database secrets** in your repository:
   - `VPS_SSH_PRIVATE_KEY`
   - `VPS_HOST`
   - `VPS_USER`
   - `HF_TOKEN` (write token for deploying `nielsr/paperswithcode-mirror`)

2. **Modify workflows** to use production database instead of test PostgreSQL service

3. **Adjust schedules** as needed for your use case

## Monitoring

- **Logs**: Cron job logs are written on the VPS under `.github/workflows/scripts/logs/`
- **Reports**: GitHub Actions shows cron trigger status and SSH wrapper failures
- **Notifications**: Configure GitHub notifications for workflow failures

## Local Testing

To test the workflows locally:

```bash
# Test database connection
uv run --env-file backend/keys.env python -m backend.database.connection test
```
