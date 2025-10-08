# Trending Papers API

## Overview

The trending papers feature uses an **Exponential Moving Average (EMA)** based algorithm to identify papers with growing GitHub star momentum. The system tracks repository star counts over time and calculates a smoothed trending score that highlights papers with sustained growth.

## API Endpoint

### GET `/api/v1/papers/trending`

Returns papers ranked by their repository trending scores.

**Base URL:** `http://your-domain.com/api/v1/papers/trending`

#### Query Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `limit` | integer | 20 | 1-100 | Maximum number of trending papers to return |
| `max_age_days` | integer | 180 | 1-365 | Maximum paper age in days (filters out older papers) |
| `min_velocity` | float | null | ≥0 | Minimum star velocity (stars/hour) threshold |

#### Response Format

```json
[
  {
    "paper_id": "51998",
    "arxiv_id": "2507.15061",
    "title": "WebShaper: Agentically Data Synthesizing...",
    "date_published": "2025-07-20",
    "repository": {
      "id": "2629",
      "url": "https://github.com/Alibaba-NLP/WebWalker",
      "owner": "Alibaba-NLP",
      "name": "WebWalker",
      "num_stars": 15549
    },
    "trending": {
      "velocity_24h": 2.143,
      "trending_score": 0.326,
      "stars_gained_24h": 66
    },
    "paper_age_days": 80.86
  }
]
```

#### Response Fields

- **paper_id**: Database ID of the paper
- **arxiv_id**: ArXiv identifier
- **title**: Paper title
- **date_published**: Publication date (ISO format)
- **repository**: GitHub repository information
  - **id**: Repository database ID
  - **url**: GitHub repository URL
  - **owner**: Repository owner
  - **name**: Repository name
  - **num_stars**: Current star count
- **trending**: Trending metrics
  - **velocity_24h**: Stars gained per hour over last 24 hours
  - **trending_score**: EMA-based trending score (higher = more trending)
  - **stars_gained_24h**: Total stars gained in last 24 hours
- **paper_age_days**: Days since publication

## How It Works

### 1. Data Collection (Hourly Cron Job)

The system runs an hourly cron job (`cron/hourly/calculate_trending_scores.py`) that:

- Takes snapshots of GitHub star counts for repositories
- Stores them in the `repository_star_history` table
- Calculates trending scores using EMA

### 2. Trending Score Calculation

The trending score uses **Exponential Moving Average (EMA)** to smooth out noise:

```
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync
trendingScore = α × rawStarsPerHour + (1 - α) × previousTrendingScore
```

Where:
- **α = 0.15** (smoothing factor)
- Low alpha means the score changes gradually
- Recent trends are weighted higher, but sudden spikes don't dominate

### 3. Database Views

The endpoint queries the `trending_papers_24h` view which:

- Joins papers with their official repositories
- Filters to recent papers (last 6 months by default)
- Only includes papers with sufficient star history
- Orders by trending score

### 4. Filtering

The view automatically filters to:
- **Latest versions only**: No duplicate paper versions
- **Official repositories only**: `is_official = TRUE` in paper_repositories
- **Recent papers only**: Published within last 6 months
- **Active trending scores**: Updated within last 24 hours

## Example API Calls

### Get top 10 trending papers
```bash
curl http://localhost:8000/api/v1/papers/trending?limit=10
```

### Get trending papers with minimum velocity
```bash
curl http://localhost:8000/api/v1/papers/trending?min_velocity=1.0&limit=20
```

### Get trending papers from last 90 days
```bash
curl http://localhost:8000/api/v1/papers/trending?max_age_days=90&limit=15
```

## Database Schema

### Tables

1. **repositories**
   - `trending_score` (NUMERIC): EMA-based trending score
   - `trending_score_updated_at` (TIMESTAMP): Last update time
   - `num_stars` (INTEGER): Current star count

2. **repository_star_history**
   - `repository_id` (BIGINT): Foreign key to repositories
   - `num_stars` (INTEGER): Star count at snapshot time
   - `snapshot_at` (TIMESTAMP): When snapshot was taken

### Views

1. **trending_repositories_24h**: All repositories ranked by trending score
2. **trending_papers_24h**: Papers ranked by their repository trending scores

## Cron Jobs

### Calculate Trending Scores (Hourly)

**Script:** `cron/hourly/calculate_trending_scores.py`

**Schedule:** Every hour

**What it does:**
- Processes 500 repositories per batch
- Calculates EMA trending scores
- Updates `repositories.trending_score`
- Runs for max 55 minutes per execution

## Implementation Files

### Database
- `/backend/database/migrations/add_trending_score.sql` - Adds trending score columns
- `/backend/database/migrations/update_trending_view_for_ema.sql` - Updates views for EMA
- `/backend/database/repos_and_pages_setup/setup_star_history.sql` - Creates history table

### Backend API
- `/backend/routers/papers.py` - Contains `/papers/trending` endpoint

### Cron Jobs
- `/cron/hourly/calculate_trending_scores.py` - Calculates EMA trending scores

## Notes

- **Data Requirements**: Requires at least 2 star count snapshots to calculate velocity
- **Startup Time**: Takes 1-2 hours after initial setup to collect sufficient data
- **Update Frequency**: Trending scores update hourly via cron job
- **Performance**: View queries are optimized with indexes on trending_score

## Migration Steps

If you need to set up trending on a new database:

1. Run the trending score migration:
```bash
psql -h localhost -U paperswithcode_user -d paperswithcode_hf \
  -f backend/database/migrations/add_trending_score.sql
```

2. Update the views:
```bash
psql -h localhost -U paperswithcode_user -d paperswithcode_hf \
  -f backend/database/migrations/update_trending_view_for_ema.sql
```

3. Set up the hourly cron job:
```bash
0 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py >> /var/log/trending_scores.log 2>&1
```

## Troubleshooting

### No trending papers returned

**Cause:** Insufficient star history data

**Solution:** Wait 1-2 hours for the cron job to collect snapshots

### Trending scores all zero

**Cause:** No star growth detected or stale data

**Solution:**
- Check cron job is running: `systemctl status cron`
- Check last update: `SELECT MAX(trending_score_updated_at) FROM repositories;`

### Stale trending scores

**Cause:** Cron job not running or failing

**Solution:**
- Check cron logs: `tail -f /var/log/trending_scores.log`
- Run manually: `uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py`
