# Hourly CRON Jobs

This directory contains CRON jobs that run hourly to keep the PapersWithCode database fresh and up-to-date.

## Active Jobs

### 1. GitHub Stars Update (`update_github_stars.py`)

**Purpose**: Fetch current GitHub star counts from the GitHub API and store historical snapshots.

**Frequency**: Every hour (0 * * * *)

**What it does**:
- Fetches GitHub star counts for repositories linked to papers
- Stores historical snapshots in `repository_star_history` table
- Prioritizes recent papers (< 6 months old) for more frequent updates
- Groups repositories by owner/name to avoid duplicate API calls
- Runs fresh and weekly queues concurrently with separate GitHub accounts

**Queue System**:
- **FRESH** (`PWC_GITHUB_TOKEN`): papers < 6 months old, oldest update first
- **WEEKLY** (`GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE`): older and
  never-updated repositories, oldest update first, refreshed every 7 days

**Configuration**:
- Max updates: up to 3,000 fresh and 1,000 weekly repositories/hour
- API delay: 1 second between calls
- Memory threshold: 200MB minimum

**Run manually**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars
```

**Required environment variables**:
- `PWC_GITHUB_TOKEN`: GitHub API token for authentication
- `GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE`: token from a separate GitHub
  account, used only for the weekly/backfill queue

---

### 2. Trending Scores Calculation (`calculate_trending_scores.py`)

**Purpose**: Calculate EMA-based trending scores from historical GitHub star data.

**Frequency**: Every hour (30 * * * *) - offset by 30 minutes from stars update

**What it does**:
- Reads historical star snapshots from `repository_star_history`
- Calculates star velocity (stars gained per hour)
- Applies Exponential Moving Average (EMA) to smooth out fluctuations
- Updates `repositories.trending_score` field

**Algorithm**:
```python
# Calculate raw velocity
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync

# Apply EMA (α = 0.75)
trendingScore = 0.75 × rawStarsPerHour + 0.25 × previousTrendingScore
```

**Configuration**:
- Batch size: 500 repositories per batch
- Update threshold: 1 hour (only update if score is > 1 hour old)
- Alpha (smoothing factor): 0.75
- Minimum snapshot interval: 0.5 hours

**Run manually**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
```

**No environment variables required** (reads from database only)

---

## Setup Instructions

### 1. Install in Crontab

```bash
# Edit crontab
crontab -e

# Add these lines (adjust paths as needed)
0 * * * * cd /root/python_projects/paperswithcode && /usr/bin/flock -n /tmp/github_stars.lock PYTHONPATH=.github/workflows /usr/bin/uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars >> /var/log/cron/github_stars.log 2>&1

30 * * * * cd /root/python_projects/paperswithcode && /usr/bin/flock -n /tmp/trending_scores.lock PYTHONPATH=.github/workflows /usr/bin/uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores >> /var/log/cron/trending_scores.log 2>&1
```

**Notes**:
- `flock -n` prevents overlapping runs (exits if already running)
- Offset by 30 minutes to avoid resource contention
- Logs are written to `/var/log/cron/` (create directory first)

### 2. Create Log Directory

```bash
sudo mkdir -p /var/log/cron
sudo chown $(whoami):$(whoami) /var/log/cron
```

### 3. Test Jobs Manually

```bash
# Test GitHub stars update
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars

# Test trending calculation
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
```

---

## Monitoring

### Check if Jobs are Running

```bash
# Check for running processes
ps aux | grep "update_github_stars\|calculate_trending"

# Check recent log entries
tail -f /var/log/cron/github_stars.log
tail -f /var/log/cron/trending_scores.log
```

### Verify Database Updates

```sql
-- Check recent star updates
SELECT owner, name, num_stars, num_stars_updated_at
FROM repositories
WHERE num_stars_updated_at >= NOW() - INTERVAL '1 hour'
ORDER BY num_stars_updated_at DESC
LIMIT 20;

-- Check recent trending score updates
SELECT owner, name, num_stars, trending_score, trending_score_updated_at
FROM repositories
WHERE trending_score_updated_at >= NOW() - INTERVAL '1 hour'
ORDER BY trending_score DESC
LIMIT 20;

-- Check snapshot creation
SELECT COUNT(*), MAX(snapshot_at)
FROM repository_star_history
WHERE snapshot_at >= NOW() - INTERVAL '1 hour';
```

---

## Performance Metrics

### Expected Performance (per hourly run)

**GitHub Stars Update**:
- Repositories processed: ~3,000 unique repos
- API calls: ~3,000 (60% of GitHub's 5K/hour limit)
- Snapshots stored: ~3,000+
- Runtime: ~50-55 minutes
- Memory usage: ~200-400MB

**Trending Calculation**:
- Repositories processed: ~500-1000
- Trending scores updated: ~500-1000
- Runtime: ~5-15 minutes
- Memory usage: ~200-300MB

### GitHub API Rate Limits

- **Limit**: 5,000 requests/hour (authenticated)
- **Our usage**: ~3,000 requests/hour (safe margin)
- **Rate limit check**: Script automatically waits if limit hit
- **Token**: Set `PWC_GITHUB_TOKEN` in `backend/keys.env`

---

## Troubleshooting

### Problem: "PWC_GITHUB_TOKEN not set"

**Solution**: Add your GitHub token to `backend/keys.env`:
```bash
echo "PWC_GITHUB_TOKEN=ghp_your_token_here" >> backend/keys.env
```

### Problem: "Rate limit hit"

**Solution**:
- Wait for rate limit to reset (checks hourly)
- Reduce `max_updates` in configuration
- Increase `delay` between API calls

### Problem: "Low memory - stopping"

**Solution**:
- Script automatically stops when < 200MB available
- Increase VPS memory if consistently hitting limit
- Reduce `batch_size` or `max_updates` in configuration

### Problem: "No more repositories to process"

**Solution**: This is normal! It means all repositories have been updated according to their priority thresholds.

### Problem: Trending scores not updating

**Solution**:
1. Check if star update script is running: `tail -f /var/log/cron/github_stars.log`
2. Verify snapshots are being created:
   ```sql
   SELECT COUNT(*) FROM repository_star_history
   WHERE snapshot_at >= NOW() - INTERVAL '24 hours';
   ```
3. Check for errors in trending log: `tail -f /var/log/cron/trending_scores.log`
4. Ensure repositories have at least 2 snapshots (needed for velocity calculation)

---

## Architecture Notes

### Why Two Separate Scripts?

**Benefits**:
1. **Separation of concerns**: API fetching vs. mathematical calculations
2. **Independent failures**: GitHub API issues don't break trending calculations
3. **Flexible scheduling**: Can run at different frequencies
4. **Scalability**: Trending calculation can process ALL repos, not just recently fetched

**Workflow**:
```
┌─────────────────────────────────────────────────────────────┐
│                    Hourly CRON Jobs                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  update_github_stars.py (every hour, :00)          │    │
│  │  ↓                                                  │    │
│  │  1. Fetch GitHub star counts via API               │    │
│  │  2. Update repositories.num_stars                  │    │
│  │  3. Store snapshot in repository_star_history      │    │
│  └────────────────────────────────────────────────────┘    │
│                           ↓                                  │
│           (Historical data accumulates in DB)               │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  calculate_trending_scores.py (every hour, :30)    │    │
│  │  ↓                                                  │    │
│  │  1. Read snapshots from repository_star_history    │    │
│  │  2. Calculate star velocity (stars/hour)           │    │
│  │  3. Apply EMA smoothing (α=0.75)                   │    │
│  │  4. Update repositories.trending_score             │    │
│  └────────────────────────────────────────────────────┘    │
│                           ↓                                  │
│              (Trending scores available for API)            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Migration from Old Scripts

If you're migrating from the previous two-script setup:

**Old scripts** (deprecated):
- ~~`update_github_stars_optimized.py`~~ → Replaced by `update_github_stars.py`
- ~~`update_github_stars_trending.py`~~ → Functionality split into both new scripts

**What changed**:
1. **Combined fetching**: Single script handles both recent and regular papers
2. **Pure calculation**: Trending calculation is now separate and database-only
3. **Better efficiency**: No duplicate API calls, cleaner architecture
4. **EMA-based**: Uses Exponential Moving Average instead of raw velocity

**Migration steps**: See `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`

---

## Additional Resources

- **Detailed guide**: `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`
- **Database schema**: `backend/database/migrations/add_trending_score.sql`
- **Service methods**: `backend/services/repository_service.py`
- **API models**: `backend/models/api.py` (Repository model includes trending_score)
