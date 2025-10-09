# Trending Papers API - Implementation Summary

## ✅ What Was Done

I've successfully updated the backend API to support the new EMA-based trending score system. The trending papers endpoint is now fully functional and integrated with the hourly cron job that calculates trending scores.

## 🔧 Changes Made

### 1. Database Migration - Updated Views

**File:** `backend/database/migrations/update_trending_view_for_ema.sql`

- Updated `trending_repositories_24h` view to use the EMA-based `repositories.trending_score` field
- Updated `trending_papers_24h` view to use the new trending score system
- Views now query pre-calculated trending scores instead of calculating on-the-fly
- Added proper filtering for recent papers (last 6 months) and active trending scores

### 2. Backend API - Fixed Endpoint Route Order

**File:** `backend/routers/papers.py`

- Moved `/papers/trending` endpoint **before** `/papers/{paper_id}` route to prevent route conflicts
- Updated endpoint documentation to reflect EMA-based calculation
- Removed duplicate endpoint definition
- Endpoint now properly returns trending papers with:
  - Paper metadata (ID, ArXiv ID, title, publication date)
  - Repository information (URL, owner, name, star count)
  - Trending metrics (velocity, trending score, stars gained)
  - Paper age filtering

### 3. Documentation

**File:** `docs/TRENDING_API.md`

Comprehensive documentation covering:
- API endpoint usage and parameters
- Response format and field descriptions
- How the EMA trending score algorithm works
- Database schema and views
- Cron job details
- Example API calls
- Troubleshooting guide

### 4. Testing

**File:** `backend/test_trending_api.py`

Created test script that validates:
- Default endpoint behavior
- Parameter filtering (limit, max_age_days, min_velocity)
- Response data structure
- Data integrity

## 📊 API Endpoint Details

### Endpoint

```
GET /api/v1/papers/trending
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Maximum number of results (1-100) |
| `max_age_days` | integer | 180 | Filter papers published within N days |
| `min_velocity` | float | null | Minimum star velocity threshold (stars/hour) |

### Example Response

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

## 🧪 Test Results

All tests passed successfully:

```
✅ Test 1: Default parameters - Retrieved 17 trending papers
✅ Test 2: Limit parameter - Retrieved 5 papers
✅ Test 3: Age filtering - Retrieved 7 papers from last 90 days
✅ Test 4: Velocity filtering - Retrieved 2 papers with velocity >= 1.0 stars/hour
```

### Top Trending Papers (Current)

1. **WebShaper** (Alibaba-NLP/WebWalker)
   - Trending Score: 0.326
   - Velocity: 2.14 stars/hour
   - Stars Gained: 66 in last 24h

2. **WebWatcher** (Alibaba-NLP/WebAgent)
   - Trending Score: 0.326
   - Velocity: 2.14 stars/hour
   - Stars Gained: 66 in last 24h

## 🔄 How It Works

### Data Flow

1. **Hourly Cron Job** (`cron/hourly/calculate_trending_scores.py`)
   - Takes snapshots of GitHub star counts
   - Stores in `repository_star_history` table
   - Calculates EMA trending scores
   - Updates `repositories.trending_score` field

2. **Database View** (`trending_papers_24h`)
   - Joins papers with repositories
   - Filters for recent papers and active scores
   - Calculates 24h velocity for display
   - Orders by trending score

3. **API Endpoint** (`/api/v1/papers/trending`)
   - Queries the view
   - Applies optional filters
   - Returns formatted JSON response

### EMA Algorithm

```
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync
trendingScore = 0.15 × rawStarsPerHour + 0.85 × previousTrendingScore
```

- **α = 0.15**: Smoothing factor (15% weight on new data, 85% on history)
- **Result**: Gradual score changes, resistant to sudden spikes
- **Benefits**: Identifies sustained growth, not just viral moments

## 📁 Modified Files

```
backend/database/migrations/update_trending_view_for_ema.sql  ← New
backend/routers/papers.py                                     ← Updated
docs/TRENDING_API.md                                          ← New
backend/test_trending_api.py                                  ← New
```

## 🚀 Using the API

### Basic Usage

```bash
# Get top 20 trending papers
curl http://localhost:8000/api/v1/papers/trending

# Get top 10 trending papers
curl http://localhost:8000/api/v1/papers/trending?limit=10

# Get trending papers from last 90 days
curl http://localhost:8000/api/v1/papers/trending?max_age_days=90

# Get highly trending papers (velocity > 1 star/hour)
curl http://localhost:8000/api/v1/papers/trending?min_velocity=1.0
```

### Frontend Integration

```typescript
// Example TypeScript/React code
interface TrendingPaper {
  paper_id: string;
  arxiv_id: string;
  title: string;
  date_published: string;
  repository: {
    id: string;
    url: string;
    owner: string;
    name: string;
    num_stars: number;
  };
  trending: {
    velocity_24h: number;
    trending_score: number;
    stars_gained_24h: number;
  };
  paper_age_days: number;
}

async function fetchTrendingPapers(limit = 20): Promise<TrendingPaper[]> {
  const response = await fetch(
    `http://localhost:8000/api/v1/papers/trending?limit=${limit}`
  );
  return await response.json();
}
```

## 📈 Database Status

Current state of trending data:
- **17 trending papers** with active scores
- **2 papers** with velocity > 1.0 stars/hour
- Top trending score: **0.326**
- Data refreshes: **Every hour** via cron job

## ✨ Key Features

1. **EMA-based Ranking**: Smooth, gradual trending scores that highlight sustained growth
2. **Flexible Filtering**: Filter by age, velocity, and result count
3. **Comprehensive Metrics**: Velocity, score, and stars gained
4. **Performance Optimized**: Pre-calculated scores with indexed views
5. **Auto-updating**: Hourly cron job keeps data fresh

## 🎯 Next Steps for Frontend

To display trending papers on the frontend:

1. **Create a Trending Page** (`frontend/src/pages/Trending.tsx`)
2. **Add API Hook** to fetch trending papers
3. **Display Cards** with trending metrics and sparklines
4. **Add Filters** for age and velocity
5. **Add Route** in `App.tsx` for `/trending`

Example hook:
```typescript
const useTrendingPapers = (limit = 20) => {
  return useQuery({
    queryKey: ['papers', 'trending', limit],
    queryFn: () => fetchTrendingPapers(limit),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};
```

## 🔍 Monitoring

To check if trending is working:

```bash
# Check trending papers count
psql -c "SELECT COUNT(*) FROM trending_papers_24h;" paperswithcode_hf

# Check latest trending scores
psql -c "SELECT MAX(trending_score_updated_at) FROM repositories;" paperswithcode_hf

# Test API endpoint
curl http://localhost:8000/api/v1/papers/trending?limit=5

# Run test suite
uv run --env-file backend/keys.env python backend/test_trending_api.py
```

## 🐛 Troubleshooting

### No papers returned
- **Cause**: Insufficient star history data
- **Fix**: Wait 1-2 hours for cron job to collect snapshots

### Stale data
- **Cause**: Cron job not running
- **Fix**: Check `systemctl status cron` and cron logs

### Route not found
- **Cause**: Server not reloaded after code changes
- **Fix**: FastAPI auto-reloads in dev mode, check logs

---

## 📝 Summary

The trending papers API is now **fully functional** and ready for frontend integration. The system:

✅ Uses EMA-based trending scores for smooth, reliable rankings
✅ Updates hourly via automated cron job
✅ Provides flexible filtering options
✅ Returns comprehensive paper and repository data
✅ Handles edge cases (no data, stale data, etc.)
✅ Is well-documented and tested

The endpoint is live at `/api/v1/papers/trending` and can be integrated into the frontend to display trending papers to users.
