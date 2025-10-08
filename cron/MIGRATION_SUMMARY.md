# GitHub Stars & Trending Migration Summary

## Date: October 8, 2025

## Overview

Successfully migrated from a two-script approach with separate optimized and trending updates to a cleaner two-phase architecture:
- **Phase 1**: Unified GitHub API fetching with historical snapshots
- **Phase 2**: Pure EMA-based trending score calculation from historical data

---

## Changes Made

### 1. Database Schema Updates

**Added columns to `repositories` table**:
```sql
- trending_score NUMERIC(10, 4) NULL
- trending_score_updated_at TIMESTAMP WITH TIME ZONE NULL
```

**Added indexes**:
```sql
- idx_repositories_trending_score (for sorting by trending score)
- idx_repositories_trending_score_updated_at (for tracking updates)
- idx_repositories_trending_refresh (composite for efficient updates)
```

**Migration file**: `backend/database/migrations/add_trending_score.sql`

✅ **Status**: Migration completed successfully (verified)

---

### 2. New CRON Scripts

#### **update_github_stars.py**
- **Replaces**: Both `update_github_stars_optimized.py` and `update_github_stars_trending.py`
- **Purpose**: Unified GitHub API fetching with priority-based updates
- **Features**:
  - Groups repos by owner/name to avoid duplicate API calls
  - Prioritizes recent papers (< 6 months) for frequent updates
  - Stores historical snapshots in `repository_star_history`
  - Memory efficient for 4GB RAM systems
- **Schedule**: Every hour (0 * * * *)
- **Location**: `cron/hourly/update_github_stars.py`

#### **calculate_trending_scores.py**
- **New script**: Pure calculation from historical data
- **Purpose**: Calculate EMA-based trending scores
- **Features**:
  - Reads from `repository_star_history` (no API calls)
  - Applies Exponential Moving Average (α = 0.15)
  - Updates `repositories.trending_score`
  - Can process ALL repositories, not just recently fetched
- **Schedule**: Every hour (30 * * * *) - offset by 30 minutes
- **Location**: `cron/hourly/calculate_trending_scores.py`

---

### 3. Code Changes

#### **Database Models** (`backend/models/database.py`)
- Added `trending_score` field to `Repository` model
- Added `trending_score_updated_at` field to `Repository` model
- Added corresponding indexes

#### **API Models** (`backend/models/api.py`)
- Added `trending_score` field to `Repository` API model
- Added `trending_score_updated_at` field to `Repository` API model

#### **Service Methods** (`backend/services/repository_service.py`)
Added new methods:
- `get_trending_repositories()` - Get trending repos sorted by score
- `update_repository_trending_score()` - Update a repository's trending score
- `get_repository_star_history()` - Get historical star counts
- Updated `_db_repository_to_api()` to include trending fields

---

### 4. Documentation

Created comprehensive documentation:

- **`cron/docs/TRENDING_EMA_GUIDE.md`**:
  - Detailed guide to EMA algorithm
  - Database schema documentation
  - Query examples
  - Migration instructions
  - Troubleshooting guide

- **`cron/hourly/README.md`**:
  - CRON job setup instructions
  - Configuration details
  - Monitoring commands
  - Troubleshooting tips

- **`cron/MIGRATION_SUMMARY.md`** (this file):
  - High-level migration summary
  - Before/after comparison
  - Action items

---

## EMA Algorithm

The trending score uses an Exponential Moving Average to smooth star growth velocity:

```python
# Calculate raw velocity
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync

# Apply EMA (α = 0.15)
trendingScore = 0.15 × rawStarsPerHour + 0.85 × previousTrendingScore
```

**Benefits**:
- Smooth, stable scores that change gradually
- Resistant to short-term spikes
- Weights recent activity more heavily
- Computationally efficient

---

## Architecture Comparison

### Before (Old Approach)

```
update_github_stars_optimized.py
  ├─ Fetch GitHub stars for ALL repos
  ├─ Update every 7 days
  └─ No trending calculation

update_github_stars_trending.py
  ├─ Fetch GitHub stars for RECENT repos
  ├─ Update every 2 hours
  ├─ Store historical snapshots
  └─ No trending calculation
```

**Issues**:
- Duplicate functionality
- No actual trending score calculation
- Historical data collected but not used
- Confusing separation of concerns

### After (New Approach)

```
update_github_stars.py
  ├─ Unified fetching for ALL repos
  ├─ Priority-based: recent (2h) vs regular (7d)
  ├─ Store historical snapshots
  └─ One script, clear purpose

calculate_trending_scores.py
  ├─ Pure calculation (no API calls)
  ├─ Read from repository_star_history
  ├─ Apply EMA algorithm
  └─ Update trending_score field
```

**Benefits**:
- Clear separation: API fetching vs. calculation
- Trending scores actually calculated and stored
- Can run independently (flexible scheduling)
- More maintainable and understandable

---

## Deprecated Scripts

The following scripts are **DEPRECATED** and should no longer be used:

- ❌ `cron/hourly/update_github_stars_optimized.py`
- ❌ `cron/hourly/update_github_stars_trending.py`

**Action**: These will be renamed with `.deprecated` extension to prevent accidental use while preserving for reference.

---

## Action Items

### ✅ Completed

1. ✅ Add `trending_score` fields to `Repository` model
2. ✅ Create SQL migration script
3. ✅ Run migration on database
4. ✅ Create `update_github_stars.py` (unified fetching)
5. ✅ Create `calculate_trending_scores.py` (EMA calculation)
6. ✅ Add service methods for trending operations
7. ✅ Update API models to include trending fields
8. ✅ Create comprehensive documentation

### 🔲 Next Steps (Manual)

1. **Update crontab** to use new scripts:
   ```bash
   # Remove old entries
   # Add new entries:
   0 * * * * /usr/bin/flock -n /tmp/github_stars.lock uv run --env-file backend/keys.env cron/hourly/update_github_stars.py >> /var/log/cron/github_stars.log 2>&1
   30 * * * * /usr/bin/flock -n /tmp/trending_scores.lock uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py >> /var/log/cron/trending_scores.log 2>&1
   ```

2. **Test the new scripts**:
   ```bash
   # Test GitHub stars fetching
   uv run --env-file backend/keys.env cron/hourly/update_github_stars.py

   # Test trending calculation
   uv run --env-file backend/keys.env cron/hourly/calculate_trending_scores.py
   ```

3. **Monitor initial runs**:
   ```bash
   # Watch logs
   tail -f /var/log/cron/github_stars.log
   tail -f /var/log/cron/trending_scores.log

   # Check database
   psql -d paperswithcode_hf -c "SELECT COUNT(*), MIN(trending_score), MAX(trending_score) FROM repositories WHERE trending_score IS NOT NULL;"
   ```

4. **Verify trending scores are being calculated**:
   ```sql
   -- Check trending repositories
   SELECT owner, name, num_stars, trending_score, trending_score_updated_at
   FROM repositories
   WHERE trending_score IS NOT NULL
   ORDER BY trending_score DESC
   LIMIT 20;
   ```

5. **Build frontend features** (future):
   - Trending papers page
   - Trending badge on paper cards
   - Star growth charts
   - API endpoint for trending papers

---

## Rollback Plan

If issues arise, you can rollback:

1. **Switch back to old scripts** in crontab
2. **Ignore trending_score columns** (they don't affect existing functionality)
3. **Remove columns if needed**:
   ```sql
   ALTER TABLE repositories DROP COLUMN IF EXISTS trending_score;
   ALTER TABLE repositories DROP COLUMN IF EXISTS trending_score_updated_at;
   ```

**Note**: Historical snapshots in `repository_star_history` are still useful for analytics even if not using trending scores.

---

## Performance Expectations

### GitHub Stars Update
- **Repos processed**: ~3,000/hour
- **API calls**: ~3,000/hour (60% of GitHub's 5K limit)
- **Runtime**: ~50-55 minutes
- **Memory**: ~200-400MB

### Trending Calculation
- **Repos processed**: ~500-1,000/hour
- **Runtime**: ~5-15 minutes
- **Memory**: ~200-300MB
- **No API calls** (reads from database only)

---

## References

- **Main guide**: `cron/docs/TRENDING_EMA_GUIDE.md`
- **Setup instructions**: `cron/hourly/README.md`
- **Database models**: `backend/models/database.py`
- **API models**: `backend/models/api.py`
- **Service methods**: `backend/services/repository_service.py`
- **Migration script**: `backend/database/migrations/add_trending_score.sql`

---

## Questions?

For questions or issues, refer to:
- Troubleshooting section in `cron/hourly/README.md`
- Algorithm details in `cron/docs/TRENDING_EMA_GUIDE.md`
- Check logs in `/var/log/cron/`
