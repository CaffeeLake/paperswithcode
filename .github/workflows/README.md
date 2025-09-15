# GitHub Actions Workflows

This directory contains GitHub Actions workflows for managing the PapersWithCode database and ArXiv synchronization.

## Workflows

### 1. Daily ArXiv Sync (`arxiv-sync.yml`)

**Purpose**: Automatically sync new papers from ArXiv API daily.

**Schedule**: Runs daily at 6:00 AM UTC

**Manual Trigger**: Can be triggered manually with optional parameters:
- `start_date`: Custom start date (YYYY-MM-DD)
- `end_date`: Custom end date (YYYY-MM-DD)  
- `dry_run`: Fetch papers without inserting them

**What it does**:
- Sets up PostgreSQL database with test data
- Runs ArXiv sync script to fetch new papers
- Generates sync report with statistics
- Uploads logs as artifacts

### 2. Test Database System (`test-database.yml`)

**Purpose**: Test database functionality on code changes.

**Triggers**: 
- Push to main/develop branches (when database files change)
- Pull requests to main branch
- Manual trigger

**What it does**:
- Sets up clean PostgreSQL database
- Tests database connection class
- Runs ArXiv sync with limited data
- Runs full test suite
- Verifies database state and queries

### 3. Import Papers Data (`import-papers.yml`)

**Purpose**: Manual import of papers data (for initial setup or bulk imports).

**Trigger**: Manual only

**Parameters**:
- `data_source`: Choose data source (papers-with-abstracts.json or custom)
- `limit`: Limit number of papers (for testing)
- `batch_size`: Processing batch size (default: 1000)
- `force_reimport`: Clear existing data before import

**What it does**:
- Sets up PostgreSQL database
- Optionally clears existing data
- Imports papers from specified data source
- Generates detailed import report

## Database Configuration

All workflows use these environment variables for database connection:
- `DB_HOST`: Database host (localhost in CI)
- `DB_PORT`: Database port (5432)
- `DB_NAME`: Database name (paperswithcode)
- `DB_USER`: Database user (postgres in CI)
- `DB_PASSWORD`: Database password (postgres in CI)

## Production Setup

For production deployment, you'll need to:

1. **Set up database secrets** in your repository:
   - `DB_HOST`: Your production database host
   - `DB_PORT`: Your production database port
   - `DB_NAME`: Your production database name
   - `DB_USER`: Your production database user
   - `DB_PASSWORD`: Your production database password

2. **Modify workflows** to use production database instead of test PostgreSQL service

3. **Adjust schedules** as needed for your use case

## Monitoring

- **Logs**: All workflows upload logs as artifacts
- **Reports**: Sync and import workflows generate detailed reports
- **Notifications**: Configure GitHub notifications for workflow failures

## Local Testing

To test the workflows locally:

```bash
# Test database connection
uv run python backend/database/db_connection.py

# Test ArXiv sync
uv run python backend/database/test_arxiv_sync.py

# Test import (with sample data)
uv run python backend/database/import_papers.py --limit 100
```
