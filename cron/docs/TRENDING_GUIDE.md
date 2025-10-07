# Trending Papers Feature Guide

## Overview

The **Trending Papers** feature tracks GitHub repository star growth over time to identify papers whose associated repositories are gaining rapid popularity. This feature uses **star velocity** (stars gained per hour) combined with **recency weighting** to calculate trending scores.

---

## Architecture

### 1. Database Schema

#### `repository_star_history` Table

Stores historical snapshots of GitHub star counts:

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

**Key Indexes:**
- `idx_star_history_repository_id` - Fast lookups by repository
- `idx_star_history_snapshot_at` - Time-based queries
- `idx_star_history_repo_time` - Composite for trending calculations

---

### 2. CRON Jobs

#### **Main GitHub Stars Job** (`update_github_stars_optimized.py`)
- **Purpose**: Update all repositories
- **Frequency**: Hourly
- **Refresh Rate**: Every 7 days per repository
- **Scope**: All repositories (50K+)
- **Priority**: Ensure fresh data for all repos

#### **Trending Stars Job** (`update_github_stars_trending.py`) ⭐ **NEW**
- **Purpose**: Track star velocity for recent papers
- **Frequency**: Hourly
- **Refresh Rate**: Every 1-2 hours per repository
- **Scope**: Only papers published in last **6 months**
- **Storage**: Creates historical snapshots for trend analysis
- **Capacity**: ~500 repositories/hour (safe for 5K GitHub rate limit)

**Why Two Jobs?**
- Main job: Comprehensive coverage, slow refresh (7 days)
- Trending job: High-frequency updates, limited scope (6 months)
- Separation prevents conflicts and optimizes API usage

---

### 3. Trending Calculation Functions

#### `calculate_star_velocity(repository_id, hours_lookback)`

Calculates stars gained per hour:

```sql
SELECT calculate_star_velocity(123, 24);
-- Returns: 2.5 (gained 60 stars in 24 hours = 2.5 stars/hour)
```

**Formula:**
```
velocity = (current_stars - stars_N_hours_ago) / N
```

#### `calculate_trending_score(repository_id, hours_lookback, recency_weight)`

Weighted trending score with time decay:

```sql
SELECT calculate_trending_score(123, 24, 2.0);
-- Returns: 250.0 (high trending score)
```

**Formula:**
```
recency_factor = exp(-hours_since_update / lookback_period * weight)
trending_score = velocity * recency_factor * 100
```

**Components:**
- **Velocity**: Absolute star gain rate
- **Recency**: Exponential decay - recent updates weighted higher
- **Scale**: Multiplied by 100 for readable scores

---

### 4. Database Views

#### `trending_repositories_24h`

```sql
SELECT * FROM trending_repositories_24h LIMIT 10;
```

**Columns:**
- `url`, `owner`, `name` - Repository identifiers
- `current_stars` - Current GitHub stars
- `velocity_24h` - Stars gained per hour (last 24h)
- `trending_score` - Weighted trending score
- `stars_24h_ago` - Star count 24 hours ago
- `stars_gained_24h` - Total stars gained in 24h

#### `trending_papers_24h`

```sql
SELECT * FROM trending_papers_24h LIMIT 10;
```

**Columns:**
- `paper_id`, `arxiv_id`, `title` - Paper identifiers
- `date_published`, `paper_age_days` - Paper age info
- `repository_url`, `owner`, `repo_name` - Repository info
- `current_stars` - Current star count
- `velocity_24h` - Star velocity
- `trending_score` - Trending score
- `stars_gained_24h` - Stars gained in 24h

**Filters:**
- Only papers published in **last 6 months**
- Only **official** repositories
- Must have snapshots from last 48 hours

---

## Setup Instructions

### 1. Database Setup

Run the setup SQL script:

```bash
cd /root/python_projects/paperswithcode
psql -U postgres -d paperswithcode_hf -f backend/database/repos_and_pages_setup/setup_star_history.sql
```

This creates:
- `repository_star_history` table
- Trending calculation functions
- Database views for trending queries
- All necessary indexes

### 2. Verify Setup

```bash
uv run --env-file backend/keys.env python -c "
from backend.database.connection import db_manager
from sqlalchemy import text

with db_manager.session_local() as session:
    # Check if table exists
    result = session.execute(text(
        'SELECT COUNT(*) FROM repository_star_history'
    )).scalar()
    print(f'✅ Star history table exists with {result} snapshots')

    # Test function
    result = session.execute(text(
        'SELECT calculate_star_velocity(1, 24)'
    )).scalar()
    print(f'✅ Functions working (velocity: {result})')
"
```

### 3. Run Trending Job Manually

Test the trending job:

```bash
# Make script executable
chmod +x cron/run_github_stars_trending.sh

# Run once to test
./cron/run_github_stars_trending.sh

# Check logs
tail -f cron/logs/github_stars_trending_$(date +%Y%m%d).log
```

### 4. Add to Crontab

Schedule the trending job to run hourly:

```bash
crontab -e
```

Add this line:

```cron
# Trending stars update (every hour)
0 * * * * cd /root/python_projects/paperswithcode && ./cron/run_github_stars_trending.sh
```

---

## Usage Examples

### Query Trending Papers

#### Top 10 Trending Papers (Last 24 Hours)

```sql
SELECT
    arxiv_id,
    title,
    current_stars,
    stars_gained_24h,
    velocity_24h,
    trending_score,
    paper_age_days
FROM trending_papers_24h
LIMIT 10;
```

#### Recent Papers with High Star Velocity

```sql
SELECT
    arxiv_id,
    title,
    date_published,
    current_stars,
    velocity_24h,
    trending_score
FROM trending_papers_24h
WHERE paper_age_days <= 30  -- Papers from last month
AND velocity_24h > 1.0      -- Gaining > 1 star/hour
ORDER BY velocity_24h DESC
LIMIT 20;
```

#### Papers Trending Right Now (Hot & New)

```sql
SELECT
    arxiv_id,
    title,
    current_stars,
    stars_gained_24h,
    trending_score,
    ROUND(paper_age_days::numeric, 1) as days_old
FROM trending_papers_24h
WHERE paper_age_days <= 7   -- Published in last week
AND trending_score > 50      -- High trending score
ORDER BY trending_score DESC
LIMIT 10;
```

### Python API Examples

#### Get Trending Papers

```python
from backend.database.connection import db_manager
from sqlalchemy import text

def get_trending_papers(limit=10, max_age_days=180):
    """Get trending papers ordered by trending score."""
    with db_manager.session_local() as session:
        query = text("""
            SELECT
                paper_id,
                arxiv_id,
                title,
                date_published,
                repository_url,
                current_stars,
                velocity_24h,
                trending_score,
                stars_gained_24h,
                paper_age_days
            FROM trending_papers_24h
            WHERE paper_age_days <= :max_age_days
            AND trending_score IS NOT NULL
            ORDER BY trending_score DESC
            LIMIT :limit
        """)

        results = session.execute(
            query,
            {"limit": limit, "max_age_days": max_age_days}
        ).fetchall()

        return [
            {
                "paper_id": row[0],
                "arxiv_id": row[1],
                "title": row[2],
                "date_published": row[3],
                "repository_url": row[4],
                "current_stars": row[5],
                "velocity_24h": float(row[6]) if row[6] else 0,
                "trending_score": float(row[7]) if row[7] else 0,
                "stars_gained_24h": row[8],
                "paper_age_days": float(row[9]) if row[9] else 0,
            }
            for row in results
        ]

# Usage
trending = get_trending_papers(limit=20, max_age_days=90)
for paper in trending:
    print(f"{paper['arxiv_id']}: {paper['title'][:60]}")
    print(f"  Stars: {paper['current_stars']} (+{paper['stars_gained_24h']} in 24h)")
    print(f"  Trending Score: {paper['trending_score']:.1f}")
    print()
```

#### Calculate Custom Trending Score

```python
def get_custom_trending_score(repository_id, hours=48, weight=3.0):
    """Calculate trending score with custom parameters."""
    with db_manager.session_local() as session:
        query = text("""
            SELECT calculate_trending_score(
                :repo_id,
                :hours,
                :weight
            )
        """)

        score = session.execute(
            query,
            {"repo_id": repository_id, "hours": hours, "weight": weight}
        ).scalar()

        return float(score) if score else 0.0

# Get trending score for repo ID 123 over last 48 hours
score = get_custom_trending_score(123, hours=48, weight=3.0)
print(f"Trending Score: {score:.2f}")
```

---

## Monitoring

### Check Job Status

```bash
# View trending job summary
uv run cron/manage_cron.py summary

# Check trending job logs
tail -100 cron/logs/github_stars_trending_$(date +%Y%m%d).log

# Count snapshots today
uv run --env-file backend/keys.env python -c "
from backend.database.connection import db_manager
from sqlalchemy import text

with db_manager.session_local() as session:
    count = session.execute(text('''
        SELECT COUNT(*) FROM repository_star_history
        WHERE snapshot_at >= CURRENT_DATE
    ''')).scalar()
    print(f'Snapshots created today: {count}')
"
```

### Verify Data Quality

```bash
uv run --env-file backend/keys.env python -c "
from backend.database.connection import db_manager
from sqlalchemy import text

with db_manager.session_local() as session:
    # Check coverage
    result = session.execute(text('''
        SELECT
            COUNT(DISTINCT r.id) as repos_with_history,
            COUNT(DISTINCT r.id) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM repository_star_history h
                    WHERE h.repository_id = r.id
                    AND h.snapshot_at >= NOW() - INTERVAL '24 hours'
                )
            ) as repos_updated_24h
        FROM repositories r
        JOIN paper_repositories pr ON r.id = pr.repository_id
        JOIN papers p ON pr.paper_id = p.id
        WHERE p.date_published >= NOW() - INTERVAL '6 months'
        AND pr.is_official = TRUE
    ''')).fetchone()

    print(f'Repositories with history: {result[0]}')
    print(f'Updated in last 24h: {result[1]}')
"
```

---

## Performance Characteristics

### Resource Usage

| Metric | Value |
|--------|-------|
| **API Calls** | ~500/hour (10% of GitHub limit) |
| **Memory** | ~300-400MB peak |
| **Runtime** | ~10-15 minutes/hour |
| **Storage** | ~50KB per snapshot |
| **Daily Snapshots** | ~12,000 (500 repos × 24 hours) |

### Coverage

| Scope | Count |
|-------|-------|
| **Total Repositories** | 50,892 |
| **Recent Papers (6mo)** | ~5,000-10,000 |
| **Official Repos** | ~3,000-5,000 |
| **Updated/Hour** | ~500 |
| **Full Cycle Time** | ~10-20 hours |

---

## Troubleshooting

### Issue: No Trending Data

**Problem:** `trending_papers_24h` view returns no results.

**Solutions:**
1. Check if trending job has run:
   ```bash
   ls -lh cron/logs/github_stars_trending_*.log
   ```

2. Verify snapshots exist:
   ```sql
   SELECT COUNT(*), MAX(snapshot_at)
   FROM repository_star_history;
   ```

3. Check if recent papers have repositories:
   ```sql
   SELECT COUNT(*) FROM papers p
   JOIN paper_repositories pr ON p.id = pr.paper_id
   WHERE p.date_published >= NOW() - INTERVAL '6 months'
   AND pr.is_official = TRUE;
   ```

### Issue: Low Trending Scores

**Problem:** All trending scores are very low (< 10).

**Explanation:** This is normal for papers with slow star growth. Trending scores scale with velocity:
- Score < 10: Slow growth (< 0.1 stars/hour)
- Score 10-50: Moderate growth (0.1-0.5 stars/hour)
- Score 50-100: High growth (0.5-1 stars/hour)
- Score > 100: Viral growth (> 1 star/hour)

**Adjust sensitivity:**
```sql
-- Lower recency weight for longer-term trends
SELECT calculate_trending_score(repo_id, 72, 1.0);  -- 72 hours, weight 1.0
```

### Issue: Job Running Slow

**Problem:** Trending job takes > 30 minutes.

**Solutions:**
1. Reduce repositories per run:
   - Edit `cron/hourly/update_github_stars_trending.py`
   - Change `max_updates = 500` to `max_updates = 300`

2. Increase API delay:
   - Change `delay = 1.2` to `delay = 1.5`

3. Check memory:
   ```bash
   free -m
   ```
   If < 300MB available, consider increasing VPS RAM.

---

## Configuration

### Adjust Trending Parameters

Edit `cron/hourly/update_github_stars_trending.py`:

```python
# Line 219-224: Configuration
delay = 1.2                 # Seconds between API calls
max_updates = 500           # Repositories per hour
threshold_hours = 2         # Update if older than N hours
min_memory_mb = 200         # Stop if memory < N MB
```

### Adjust Trending Score Calculation

Modify database function:

```sql
-- More weight on recency (default: 2.0)
SELECT calculate_trending_score(repo_id, 24, 3.0);  -- Higher weight = more recency focus

-- Longer lookback period (default: 24 hours)
SELECT calculate_trending_score(repo_id, 72, 2.0);  -- 3-day trend
```

---

## API Integration

### FastAPI Endpoint (Example)

```python
# backend/routers/trending.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database.connection import get_db
from sqlalchemy import text

router = APIRouter()

@router.get("/papers/trending")
async def get_trending_papers(
    limit: int = 20,
    max_age_days: int = 180,
    db: Session = Depends(get_db)
):
    """Get trending papers based on repository star velocity."""
    query = text("""
        SELECT * FROM trending_papers_24h
        WHERE paper_age_days <= :max_age_days
        ORDER BY trending_score DESC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {"limit": limit, "max_age_days": max_age_days}
    ).fetchall()

    return {
        "count": len(results),
        "results": [
            {
                "paper_id": row.paper_id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
                "stars": row.current_stars,
                "velocity": float(row.velocity_24h or 0),
                "trending_score": float(row.trending_score or 0),
                "stars_gained_24h": row.stars_gained_24h,
            }
            for row in results
        ]
    }
```

---

## Future Enhancements

1. **Multiple Time Windows**
   - Add 12-hour, 48-hour, 7-day trending views
   - Compare velocity across different time periods

2. **Trending Categories**
   - Calculate trending scores per ArXiv category
   - Filter trending by primary research area

3. **Trending Threshold Alerts**
   - Notify when paper crosses velocity threshold
   - Email digest of top trending papers

4. **Historical Trending**
   - Store trending scores over time
   - Show "previously trending" papers
   - Trending history graphs

5. **Smart Refresh Rate**
   - Increase frequency for papers with high velocity
   - Reduce frequency for stable papers
   - Adaptive scheduling based on growth patterns

---

## Summary

The trending feature provides real-time insights into paper popularity by tracking GitHub star growth velocity. By combining frequent updates (hourly) with historical snapshots, it enables identification of papers gaining rapid traction in the community.

**Key Benefits:**
- ✅ Real-time trending detection
- ✅ Recency-weighted scoring
- ✅ Efficient API usage (separate jobs)
- ✅ Scalable architecture
- ✅ Flexible queries via SQL views

**Next Steps:**
1. Run database setup script
2. Test trending job manually
3. Add to crontab for hourly execution
4. Monitor job status and data quality
5. Integrate trending endpoint into API
