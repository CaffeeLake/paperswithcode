# Frontend Trending Papers Implementation

## Summary

Updated the frontend to use the new `/api/v1/papers/trending` backend endpoint for displaying trending papers based on GitHub star velocity using Exponential Moving Average (EMA).

## Changes Made

### 1. API Client Updates (`frontend/src/lib/api.ts`)

#### Added TypeScript Interfaces:
```typescript
export interface TrendingMetrics {
  velocity_24h: number;
  trending_score: number;
  stars_gained_24h: number;
}

export interface TrendingPaper {
  paper_id: string;
  arxiv_id: string;
  title: string;
  date_published: string | null;
  repository: {
    id: string;
    url: string;
    owner: string;
    name: string;
    num_stars: number;
  };
  trending: TrendingMetrics;
  paper_age_days: number;
}
```

#### Added API Method:
```typescript
async getTrendingPapers(params?: {
  limit?: number;
  max_age_days?: number;
  min_velocity?: number;
}): Promise<TrendingPaper[]>
```

### 2. Custom Hook (`frontend/src/hooks/usePapers.ts`)

Added `useTrendingPapers` hook with TanStack Query:
- Default limit: 20 papers
- Default max_age_days: 180 days
- Shorter stale time (2 minutes) for fresher trending data
- Conditional enablement based on UI state

### 3. Papers Page Updates (`frontend/src/pages/Papers.tsx`)

#### Key Features:
1. **Conditional Endpoint Usage**:
   - Uses `/papers/trending` when sortBy is 'trending' AND no search term
   - Falls back to regular `/papers` endpoint when searching with trending selected

2. **Data Transformation**:
   - Added `transformTrendingPaperForUI()` helper function
   - Handles different data structure from trending endpoint
   - Maps repository information to UI format

3. **UI Improvements**:
   - Disabled infinite scroll for trending papers (fixed list of top papers)
   - Shows "Showing top X trending papers" indicator
   - Proper loading and error states for both endpoints

#### Logic Flow:
```typescript
const useTrendingEndpoint = sortBy === 'trending' && !debouncedSearchTerm;

// Conditionally fetch from appropriate endpoint
const trendingQuery = useTrendingPapers({ enabled: useTrendingEndpoint });
const infiniteQuery = useInfinitePapers({ enabled: !useTrendingEndpoint });

// Merge results based on active endpoint
if (useTrendingEndpoint) {
  transformedPapers = trendingData.map(transformTrendingPaperForUI);
} else {
  transformedPapers = infiniteData.pages.flatMap(...).map(transformPaperForUI);
}
```

## API Endpoint Details

### Request
```
GET /api/v1/papers/trending
```

### Query Parameters
- `limit` (optional, default: 20, range: 1-100) - Number of papers to return
- `max_age_days` (optional, default: 180, range: 1-365) - Maximum paper age
- `min_velocity` (optional) - Minimum star velocity threshold

### Response Format
```json
[
  {
    "paper_id": "51302",
    "arxiv_id": "2506.16655",
    "title": "Arch-Router: Aligning LLM Routing with Human Preferences",
    "date_published": "2025-06-19",
    "repository": {
      "id": "156562",
      "url": "https://github.com/katanemo/archgw/",
      "owner": "katanemo",
      "name": "archgw",
      "num_stars": 3851
    },
    "trending": {
      "velocity_24h": 2.12,
      "trending_score": 2.121249382011747,
      "stars_gained_24h": 92
    },
    "paper_age_days": 112.31
  }
]
```

## Trending Score Algorithm

The backend uses an **Exponential Moving Average (EMA)** algorithm:

1. **Velocity Calculation**: `(current_stars - previous_stars) / hours_elapsed`
2. **EMA Formula**: `trending_score = α × velocity + (1 - α) × previous_score`
3. **Smoothing Factor**: α = 0.15 (85% weight on historical trend, 15% on new data)

This approach:
- Reduces noise from sudden spikes
- Weights recent trends more heavily
- Provides smooth, gradual score changes
- Requires hourly cron job for updates

## User Experience

### When "Trending" Tab is Selected:
1. **Without Search**: Shows top 50 trending papers from dedicated endpoint
2. **With Search**: Falls back to regular endpoint with date sorting (search within trending)

### Visual Indicators:
- 🔥 Trending tab with orange highlight
- GitHub stars displayed prominently
- "Showing top X trending papers" message at bottom
- No infinite scroll (fixed list of top papers)

## Testing

### Backend Endpoint Test:
```bash
curl "http://167.235.148.241:8000/api/v1/papers/trending?limit=5"
```

### Frontend:
1. Navigate to http://localhost:8080
2. Click "🔥 Trending" tab
3. Verify papers are sorted by trending score
4. Verify GitHub stars are displayed
5. Test search functionality maintains trending context

## Dependencies

- **Backend**: `/api/v1/papers/trending` endpoint must be running
- **Cron Job**: Hourly trending score calculation must be active
- **Database**: `trending_papers_24h` view must exist

## Future Enhancements

1. Fetch full paper details (authors, abstract, tasks) for trending papers
2. Add trending score indicator/badge on paper cards
3. Show velocity trends (up/down arrows)
4. Add time range filters (24h, 7d, 30d trending)
5. Cache trending results more aggressively

## Related Files

- `frontend/src/lib/api.ts` - API client
- `frontend/src/hooks/usePapers.ts` - React Query hooks
- `frontend/src/pages/Papers.tsx` - Main papers page
- `backend/routers/papers.py` - Backend endpoint
- `cron/hourly/calculate_trending_scores.py` - Score calculation
- `backend/database/migrations/update_trending_view_for_ema.sql` - Database views

## Notes

- Trending endpoint returns papers with GitHub repositories only
- Scores update hourly via cron job
- Papers must be within max_age_days threshold (default 180 days)
- Limited to 100 papers per request (backend constraint)
