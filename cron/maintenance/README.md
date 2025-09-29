# GitHub Repository Cleanup

This directory contains scripts to clean up invalid GitHub repositories from the database.

## Overview

Over time, GitHub repositories can become invalid due to various reasons:
- Repository deleted by owner
- Repository made private
- Repository disabled/suspended
- Account deleted or suspended

These invalid repositories cause the GitHub stars update cron job to fail or waste API calls. This cleanup script identifies and removes such repositories from the database.

## Files

- `cleanup_invalid_repositories.py` - Main cleanup script
- `run_cleanup_invalid_repositories.sh` - Shell wrapper with safety features
- `README.md` - This documentation

## Features

### Safety Features
- **Dry-run mode by default** - Never deletes anything unless explicitly requested
- **Comprehensive backup** - All removed repositories are backed up to JSON files
- **Memory monitoring** - Stops if system memory is low
- **Rate limiting** - Conservative 2.5s delays (shared token with stars update job)
- **Confirmation prompts** - Requires explicit confirmation for live mode

### Efficiency Features
- **Grouped processing** - Groups repositories by owner/name to minimize API calls
- **Smart prioritization** - Checks low-star repositories first (more likely to be invalid)
- **Memory efficient** - Designed for 4GB VPS environments
- **Progress tracking** - Detailed logging and statistics

### Error Handling
- **404 Detection** - Identifies repositories that no longer exist
- **403 Handling** - Distinguishes between private repos and rate limits
- **API Error Recovery** - Graceful handling of network issues
- **Backup on failure** - Data is backed up before any deletion

## Usage

### Recommended Workflow

1. **Start with a dry run to assess the situation:**
   ```bash
   ./cron/maintenance/run_cleanup_invalid_repositories.sh --limit 100
   ```

2. **Review the logs and statistics:**
   ```bash
   tail -f cron/logs/cleanup_invalid_repositories_*.log
   ```

3. **If satisfied, run a small live cleanup:**
   ```bash
   ./cron/maintenance/run_cleanup_invalid_repositories.sh --live --limit 50
   ```

4. **For full cleanup (use with caution):**
   ```bash
   ./cron/maintenance/run_cleanup_invalid_repositories.sh --live
   ```

### Command Options

#### Shell Wrapper (`run_cleanup_invalid_repositories.sh`)
```bash
# Dry run (safe, default)
./run_cleanup_invalid_repositories.sh

# Dry run with limit
./run_cleanup_invalid_repositories.sh --limit 100

# Live cleanup with limit
./run_cleanup_invalid_repositories.sh --live --limit 50

# Live cleanup without confirmation
./run_cleanup_invalid_repositories.sh --live --force

# Show help
./run_cleanup_invalid_repositories.sh --help
```

#### Direct Python Script
```bash
# Dry run (default)
uv run --env-file backend/keys.env cron/maintenance/cleanup_invalid_repositories.py

# Live mode
uv run --env-file backend/keys.env cron/maintenance/cleanup_invalid_repositories.py --live

# With limit
uv run --env-file backend/keys.env cron/maintenance/cleanup_invalid_repositories.py --limit 100
```

## How It Works

### Repository Detection
1. **Query unique repositories** - Groups by owner/name to avoid duplicate API calls
2. **Prioritize by likelihood** - Checks low-star repositories first
3. **GitHub API check** - Makes GET request to check repository existence
4. **Ultra-safe response classification**:
   - 200: Repository exists and is accessible ✅ **KEEP**
   - 404: Repository definitively not found ❌ **REMOVE**
   - 403: Could be private repo OR rate limit ✅ **KEEP** (ultra-conservative)
   - 451: Legal reasons (might be temporary) ✅ **KEEP** (ultra-conservative)
   - All other responses: Unknown issue ✅ **KEEP** (ultra-conservative)

**CRITICAL SAFETY**: The script ONLY removes repositories on 404 responses to eliminate any risk of removing valid repositories due to rate limiting, API issues, or private repositories.

### Removal Process
1. **Backup first** - All repository data saved to JSON backup file
2. **Group removal** - All URLs for the same repository removed together
3. **Atomic operation** - Either all URLs removed or none
4. **Detailed logging** - Every action logged with timestamps

### Statistics Tracking
- Total unique repositories in database
- Number of repositories checked
- Invalid repositories found
- Repository URLs removed
- API calls made and errors encountered
- Processing rate and efficiency metrics

## Output Files

### Log Files
Located in `cron/logs/cleanup_invalid_repositories_YYYYMMDD_HHMMSS.log`

Contains:
- Detailed execution log
- Progress updates every 25 repositories
- Final statistics summary
- Error messages and warnings

### Backup Files
Located in `cron/logs/removed_repositories_backup_YYYYMMDD_HHMMSS.json`

Contains:
- Complete repository data before removal
- Removal reason and timestamp
- Can be used to restore repositories if needed

Example backup structure:
```json
[
  {
    "timestamp": "2025-09-29T10:30:00",
    "dry_run": false,
    "repositories": [
      {
        "id": 12345,
        "url": "https://github.com/user/repo",
        "owner": "user",
        "name": "repo",
        "num_stars": 0,
        "removal_reason": "Repository not found (404)",
        "removed_at": "2025-09-29T10:30:00"
      }
    ]
  }
]
```

## Performance Characteristics

### API Usage
- **Rate limit**: 1 request per second (3,600/hour)
- **Efficiency**: Groups multiple URLs per repository
- **Typical savings**: 10-100x fewer API calls than naive approach

### Memory Usage
- **Optimized for 4GB VPS**
- **Memory monitoring**: Stops if <200MB available
- **Garbage collection**: Regular cleanup to prevent memory leaks

### Processing Speed
- **~25 repositories per minute** (with 1s delays)
- **~1,500 repositories per hour** maximum
- **Actual speed depends on**: API response times, invalid repository rate

## Troubleshooting

### Common Issues

1. **"PWC_GITHUB_TOKEN not set"**
   - Ensure GitHub token is in `backend/keys.env`
   - Token needs repo read permissions

2. **"Insufficient memory"**
   - Free up system memory
   - Reduce processing limit with `--limit`

3. **"Rate limit hit"**
   - Script automatically waits and retries
   - Consider running during off-peak hours

4. **Database connection errors**
   - Check PostgreSQL is running
   - Verify database credentials in `backend/keys.env`

### Recovery

If you need to restore removed repositories:

1. **Find the backup file**:
   ```bash
   ls -la cron/logs/removed_repositories_backup_*.json
   ```

2. **Review the backup data**:
   ```bash
   jq '.[].repositories[] | {url, owner, name, removal_reason}' backup_file.json
   ```

3. **Restore if needed** (manual SQL insertion required):
   ```sql
   INSERT INTO repositories (url, owner, name, num_stars, source, created_at)
   VALUES (...);
   ```

## Integration with Existing Cron Jobs

This cleanup script is designed to complement the existing GitHub stars update job:

### Rate Limit Coordination
- **Shared GitHub token**: Both scripts use the same `PWC_GITHUB_TOKEN`
- **Total API limit**: 5,000 requests/hour ([GitHub docs](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2022-11-28))
- **Stars update usage**: ~3,000 requests/hour (runs hourly)
- **Cleanup allocation**: ~1,400 requests/hour (conservative with 2.5s delays)

### Scheduling Recommendations
1. **Run cleanup during off-hours** when stars update is less active
2. **Monitor both job logs** for rate limit conflicts
3. **Use smaller limits** (`--limit 100-500`) for regular maintenance
4. **Schedule weekly/monthly** rather than daily to minimize API pressure

### Performance Expectations
- **Hourly capacity**: ~600 repositories (with 2.5s delays)
- **Daily capacity**: ~2,000-5,000 repositories (depending on scheduling)
- **API efficiency**: Groups multiple URLs per repository to minimize calls

## Best Practices

### Before Running
- [ ] Check system memory availability
- [ ] Verify GitHub API token is valid
- [ ] Run dry-run first to assess scope
- [ ] Review recent GitHub stars update logs for error patterns

### During Execution
- [ ] Monitor log files for progress
- [ ] Watch system memory usage
- [ ] Be prepared to interrupt if needed (Ctrl+C)

### After Execution
- [ ] Review final statistics
- [ ] Check backup files are created
- [ ] Monitor next GitHub stars update job for improvements
- [ ] Archive old log files periodically

## Security Considerations

- **GitHub token**: Keep secure, use minimal required permissions
- **Backup files**: Contain repository data, handle according to data policies
- **Log files**: May contain repository URLs, consider retention policies
- **Database access**: Uses existing database credentials, no additional permissions needed
