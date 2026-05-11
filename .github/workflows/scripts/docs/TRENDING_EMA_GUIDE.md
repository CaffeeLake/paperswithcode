# EMA-Based Trending Papers Implementation Guide

## Overview

The **Trending Papers** feature uses an **Exponential Moving Average (EMA)** to calculate trending scores based on GitHub repository star growth. This approach provides smooth, stable trending metrics that weight recent activity more heavily while filtering out short-term volatility.

---

## Architecture

### 1. Two-Phase Approach

The system is split into two independent CRON jobs:

#### **Phase 1: GitHub Stars Fetching** (`update_github_stars.py`)
- **Purpose**: Fetch current GitHub star counts from GitHub API
- **Frequency**: Hourly
- **Output**: Updates `repositories.num_stars` and stores historical snapshots in `repository_star_history`

#### **Phase 2: Trending Score Calculation** (`calculate_trending_scores.py`)
- **Purpose**: Calculate EMA-based trending scores from historical data
- **Frequency**: Hourly (runs independently of Phase 1)
- **Output**: Updates `repositories.trending_score` based on star velocity

### Why Two Scripts?

1. **Separation of Concerns**: API fetching vs. mathematical calculations
2. **Flexibility**: Trending calculation can run more/less frequently than API fetching
3. **Resilience**: GitHub API failures don't affect trending score updates
4. **Efficiency**: Can calculate trends for ALL repositories, not just recently fetched ones

---

## Database Schema

### `repositories` Table Extensions

```sql
ALTER TABLE repositories
ADD COLUMN trending_score NUMERIC(10, 4) NULL,
ADD COLUMN trending_score_updated_at TIMESTAMP WITH TIME ZONE NULL;

-- Indexes for efficient querying
CREATE INDEX idx_repositories_trending_score
ON repositories(trending_score DESC NULLS LAST);

CREATE INDEX idx_repositories_trending_score_updated_at
ON repositories(trending_score_updated_at);
```

### `repository_star_history` Table

```sql
CREATE TABLE repository_star_history (
    id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT REFERENCES repositories(id),
    num_stars INTEGER NOT NULL,
    snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(repository_id, snapshot_at)
);
```

---

## EMA Trending Algorithm

### Formula

The trending score is calculated using an Exponential Moving Average:

```
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync

trendingScore = α × rawStarsPerHour + (1 - α) × previousTrendingScore
```

Where:
- **α = 0.75** (smoothing factor)
- **hoursSinceLastSync** = time between snapshots (in hours)
- **previousTrendingScore** = the trending score from last calculation (or `rawStarsPerHour` if first time)

### Why α = 0.75?

- **High alpha (0.75)** means 25% weight on historical average, 75% on new data
- **Benefits**:
  - Rankings respond quickly to recent star velocity changes
  - Newly trending repositories surface fast
  - Some smoothing is retained to avoid wild single-hour swings
  - Trade-off: more sensitive to short-term spikes than a low-alpha EMA

### Example Calculation

```python
# Previous state
previous_stars = 1000
previous_trending_score = 4.5  # stars/hour

# New snapshot (24 hours later)
current_stars = 1120
hours_elapsed = 24

# Calculate raw velocity
raw_stars_per_hour = (1120 - 1000) / 24 = 5.0 stars/hour

# Apply EMA
trending_score = 0.75 × 5.0 + 0.25 × 4.5
                = 3.75 + 1.125
                = 4.875 stars/hour
```

---

## CRON Job Details

### Job 1: `update_github_stars.py`

**Purpose**: Fetch GitHub stars and store snapshots

**Configuration**:
```python
delay = 1.0  # 1 second between API calls
max_updates = 3000  # Process up to 3000 repos/hour
threshold_hours_recent = 2  # Update recent papers every 2 hours
threshold_days_regular = 7  # Update regular papers every 7 days
```

**Priority System**:
1. **NEW** (Priority 1): Never-updated repositories
2. **RECENT** (Priority 2): Papers < 6 months old (update every 2 hours)
3. **REGULAR** (Priority 3): Papers > 6 months old (update every 7 days)

**Output**:
- Updates `repositories.num_stars`
- Updates `repositories.num_stars_updated_at`
- Creates entries in `repository_star_history`

**Example Run**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars
```

### Job 2: `calculate_trending_scores.py`

**Purpose**: Calculate EMA trending scores from historical data

**Configuration**:
```python
batch_size = 500  # Process 500 repos per batch
update_threshold_hours = 1  # Update if score > 1 hour old
ALPHA = 0.75  # EMA smoothing factor
MIN_HOURS_BETWEEN_SNAPSHOTS = 0.5  # Minimum time between snapshots
```

**Algorithm**:
1. Find repositories with snapshots but outdated/missing trending scores
2. Get last 2 snapshots for each repository
3. Calculate raw stars per hour (velocity)
4. Apply EMA formula to calculate new trending score
5. Store updated trending score in database

**Output**:
- Updates `repositories.trending_score`
- Updates `repositories.trending_score_updated_at`

**Example Run**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
```

---

## API Integration

### Service Methods

The `RepositoryService` provides methods for working with trending scores:

```python
from backend.services.repository_service import RepositoryService

# Get trending repositories
trending_repos = repo_service.get_trending_repositories(
    page=1,
    page_size=50,
    min_score=0.1,  # Minimum 0.1 stars/hour
    max_age_days=180  # Only papers from last 6 months
)

# Get star history for a repository
history = repo_service.get_repository_star_history(
    repository_id=123,
    hours_lookback=168  # Last 7 days
)
```

### API Model

The `Repository` API model includes trending fields:

```python
class Repository(BaseModel):
    id: str
    url: str
    owner: Optional[str]
    name: Optional[str]
    num_stars: int
    trending_score: Optional[float]  # Stars per hour (EMA)
    trending_score_updated_at: Optional[datetime]
    # ... other fields
```

---

## Querying Trending Papers

### Get Top Trending Repositories

```sql
SELECT
    r.id,
    r.owner,
    r.name,
    r.num_stars,
    r.trending_score,
    r.trending_score_updated_at,
    COUNT(DISTINCT p.id) as paper_count
FROM repositories r
JOIN paper_repositories pr ON r.id = pr.repository_id
JOIN papers p ON pr.paper_id = p.id
WHERE r.trending_score IS NOT NULL
AND r.trending_score > 0.1
AND p.date_published >= NOW() - INTERVAL '6 months'
AND p.is_latest_version = TRUE
GROUP BY r.id, r.owner, r.name, r.num_stars, r.trending_score, r.trending_score_updated_at
ORDER BY r.trending_score DESC
LIMIT 50;
```

### Get Trending Papers (Deduplicated)

```sql
-- When multiple papers link to same repo, show only the highest-cited one
WITH ranked_papers AS (
    SELECT
        p.*,
        r.trending_score,
        r.owner,
        r.name,
        ROW_NUMBER() OVER (
            PARTITION BY r.owner, r.name
            ORDER BY p.citation_count DESC, p.date_published DESC
        ) as rn
    FROM papers p
    JOIN paper_repositories pr ON p.id = pr.paper_id
    JOIN repositories r ON pr.repository_id = r.id
    WHERE r.trending_score IS NOT NULL
    AND r.trending_score > 0.1
    AND p.date_published >= NOW() - INTERVAL '6 months'
    AND p.is_latest_version = TRUE
    AND pr.is_official = TRUE
)
SELECT *
FROM ranked_papers
WHERE rn = 1
ORDER BY trending_score DESC
LIMIT 50;
```

---

## Performance Characteristics

### Update Frequencies

| Repository Type | GitHub API Fetch | Trending Calculation |
|----------------|------------------|---------------------|
| Recent papers (< 6 months) | Every 2 hours | Every 1 hour |
| Regular papers (> 6 months) | Every 7 days | Every 1 hour |
| All repositories | ~3000/hour | ~500/hour |

### API Usage

- **GitHub API Rate Limit**: 5,000 requests/hour (with token)
- **Our Usage**: ~3,000 requests/hour (60% of limit, safe margin)
- **Efficiency Gain**: 1 API call can update multiple repository URLs (grouped by owner/name)

### Memory Requirements

- **Stars Update**: ~200MB minimum available memory
- **Trending Calculation**: ~200MB minimum available memory
- **Optimized for**: 4GB RAM VPS environments

---

## Migration Guide

### Replacing Old Scripts

**Before** (2 scripts):
- `update_github_stars_optimized.py` - General updates every 7 days
- `update_github_stars_trending.py` - Recent papers every 2 hours

**After** (2 scripts):
- `update_github_stars.py` - **Combined** fetching with priority system
- `calculate_trending_scores.py` - **Pure calculation** from historical data

### Migration Steps

1. **Add new columns**:
   ```bash
   psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_trending_score.sql
   ```

2. **Run initial trending calculation**:
   ```bash
   PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
   ```

3. **Schedule the current jobs**:
   ```cron
   0 * * * * /usr/bin/flock -n /tmp/github_stars.lock PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars >> /var/log/cron/github_stars.log 2>&1
   15 * * * * /usr/bin/flock -n /tmp/trending_scores.lock PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores >> /var/log/cron/trending_scores.log 2>&1
   ```

GitHub Actions is the production scheduler in this repository; the crontab
example is only useful for manual VPS scheduling.

---

## Monitoring & Debugging

### Check Trending Scores

```sql
-- Repositories with highest trending scores
SELECT owner, name, num_stars, trending_score, trending_score_updated_at
FROM repositories
WHERE trending_score IS NOT NULL
ORDER BY trending_score DESC
LIMIT 20;

-- Repositories with recent score updates
SELECT owner, name, trending_score, trending_score_updated_at
FROM repositories
WHERE trending_score_updated_at >= NOW() - INTERVAL '1 hour'
ORDER BY trending_score DESC;
```

### Check Historical Data

```sql
-- Star growth over last 7 days for a repository
SELECT
    snapshot_at,
    num_stars,
    num_stars - LAG(num_stars) OVER (ORDER BY snapshot_at) as stars_gained
FROM repository_star_history
WHERE repository_id = 123
AND snapshot_at >= NOW() - INTERVAL '7 days'
ORDER BY snapshot_at DESC;
```

### Verify EMA Calculation

```python
# Check if EMA is being calculated correctly
from backend.database.connection import db_manager

session = db_manager.session_local()

# Get a repository with history
repo_id = 123
snapshots = session.execute("""
    SELECT num_stars, snapshot_at
    FROM repository_star_history
    WHERE repository_id = :repo_id
    ORDER BY snapshot_at DESC
    LIMIT 2
""", {"repo_id": repo_id}).fetchall()

# Calculate expected trending score
if len(snapshots) >= 2:
    current_stars, current_time = snapshots[0]
    prev_stars, prev_time = snapshots[1]
    hours_elapsed = (current_time - prev_time).total_seconds() / 3600
    raw_velocity = (current_stars - prev_stars) / hours_elapsed

    # Get current trending score
    current_score = session.execute("""
        SELECT trending_score
        FROM repositories
        WHERE id = :repo_id
    """, {"repo_id": repo_id}).fetchone()[0]

    # Calculate what it should be
    # For first calculation: trending_score = raw_velocity
    # For subsequent: trending_score = 0.75 * raw_velocity + 0.25 * previous_score

    print(f"Raw velocity: {raw_velocity:.4f} stars/hour")
    print(f"Current trending score: {current_score:.4f}")
```

---

## Advantages of EMA Approach

### Over Simple Velocity
- ✅ Smooths out random fluctuations
- ✅ More stable rankings
- ✅ Gradual adaptation to changes
- ✅ Better reflects sustained trends vs. temporary spikes

### Over Time-Windowed Averaging
- ✅ No arbitrary window size selection
- ✅ Automatically weights recent data more
- ✅ Computationally efficient (only needs 2 data points)
- ✅ Memory efficient (no need to store long histories)

### Over Complex ML Models
- ✅ Simple, interpretable formula
- ✅ No training required
- ✅ Predictable behavior
- ✅ Fast computation

---

## Future Enhancements

### Possible Improvements
1. **Adaptive Alpha**: Adjust α based on paper age or volatility
2. **Multi-timeframe Analysis**: Different EMAs for short/medium/long term trends
3. **Decay Function**: Apply time decay to very old papers
4. **Composite Scoring**: Combine trending score with citation velocity
5. **Category-Specific Trending**: Normalize scores within paper categories

### Frontend Integration
- **Trending Tab**: Display papers sorted by trending score
- **Trending Badge**: Visual indicator for high-trending papers
- **Trend Chart**: Historical star growth visualization
- **Velocity Indicator**: Arrow showing up/down/stable trends

---

## References

- **Exponential Moving Average**: https://en.wikipedia.org/wiki/Moving_average#Exponential_moving_average
- **HuggingFace Papers Trending**: Inspiration for this implementation
- **Original Implementation**: Based on user research of hf.co/papers trending algorithm
