# Benchmark Leaderboard Updates

## Summary

Updated the benchmark leaderboard page to match the PapersWithCode.com design with improved data display, better chart visualization, and enhanced table columns.

## Changes Made

### 1. Backend API Updates (`backend/`)

#### `backend/models/api.py`
- **Added new fields to `Evaluation` model:**
  - `paper_title`: Optional[str] - Title of the paper
  - `code_url`: Optional[str] - URL to the code repository (GitHub)
  - `result_url`: Optional[str] - URL to the result/demo page

#### `backend/services/evaluation_service.py`
- **Added `_get_paper_info()` helper method:**
  - Joins with `papers` table to get paper title
  - Joins with `repositories` and `paper_repositories` tables to get GitHub URL
  - Prefers official repositories when multiple are available
- **Updated all evaluation methods to include new fields:**
  - `get_evaluations()` - Paginated list with paper info
  - `get_evaluation()` - Single evaluation with paper info
  - `create_evaluation()` - Creation with paper info
- **Result:** API now returns paper titles and repository links with every evaluation

### 2. Frontend Updates (`frontend/`)

#### `frontend/src/lib/api.ts`
- **Updated `Evaluation` interface:**
  - Added `paper_title?: string`
  - Added `code_url?: string`
  - Added `result_url?: string`

#### `frontend/src/pages/Benchmark.tsx`
- **Updated imports:**
  - Changed from `ScatterChart` to `LineChart` for better visualization
  - Added `Select` components for filtering
  - Added `CheckCircle` icon for result column

- **Added filter controls:**
  - **View** dropdown - Select metric to display (AP, AP50, AP75, etc.)
  - **by** dropdown - Sort by Date or Score
  - **for** dropdown - Filter for "All models" or "Top models"

- **Updated chart visualization:**
  - Changed from scatter plot to line chart with dots
  - Each evaluation is now a separate dot on the chart
  - X-axis shows dates (formatted as "MMM YY")
  - Y-axis shows the selected metric value
  - Blue line connects top performing models chronologically
  - Added legend showing "Other models" (gray) vs "Models with highest metric" (blue)

- **Updated badge:**
  - Changed "Benchmark Leaderboard" → "State-of-the-Art Leaderboard"
  - Blue background color matching PapersWithCode design

- **Updated table columns:**
  | Old Columns | New Columns |
  |-------------|-------------|
  | Rank | Rank ✓ |
  | Model | Model ✓ |
  | Metric | Metric (dynamic based on selection) ✓ |
  | Paper (just "View" link) | **Paper (actual title as link)** ✓ |
  | Task | **Code (GitHub icon)** ✓ |
  | Additional Data | **Result (checkmark icon)** ✓ |
  | Date | **Year** ✓ |
  | - | **Tags** (task + extra data badge) ✓ |

- **Paper column improvements:**
  - Now displays actual paper title (truncated at 60 chars if needed)
  - Links to `/paper/{paper_id}` page
  - Falls back to "View" link if title not available

- **Code column:**
  - Shows GitHub icon when code URL is available
  - Links directly to repository
  - Hover effect for better UX
  - Shows "-" when no code available

- **Result column:**
  - Shows checkmark icon when result URL is available
  - Links to external results page
  - Shows "-" when no results available

### 3. Database Script (`backend/database/`)

#### `backend/database/fix_benchmark_issues.py`
- Created script to find and remove evaluations with score 0
- Verified database integrity
- **Result:** No evaluations with score 0 found (database is clean)

## API Response Example

```json
{
  "id": "3",
  "paper_id": "11558",
  "model_name": "Co-DETR",
  "metrics": {
    "box AP": "65.9",
    "Params (M)": "348"
  },
  "best_metric": "box AP",
  "evaluated_on": "2022-11-22",
  "paper_title": "DETRs with Collaborative Hybrid Assignments Training",
  "code_url": "https://github.com/siyuanliii/masa",
  "result_url": "https://arxiv.org/abs/2211.12860v5"
}
```

## Testing

1. **Backend API:**
   ```bash
   curl http://localhost:8000/api/v1/evaluations/?page_size=1
   ```
   ✅ Returns paper_title and code_url fields

2. **Frontend:**
   - Navigate to `http://localhost:8080/benchmark/coco-common-objects-in-context`
   - ✅ Chart displays individual dots for each evaluation
   - ✅ Filter controls work (View, by, for)
   - ✅ Table shows paper titles as links
   - ✅ Code column shows GitHub icons with working links
   - ✅ Result column shows checkmark icons
   - ✅ Tags column displays task and extra data badges

## Files Modified

### Backend
- `backend/models/api.py`
- `backend/services/evaluation_service.py`

### Frontend
- `frontend/src/lib/api.ts`
- `frontend/src/pages/Benchmark.tsx`

### Database Scripts
- `backend/database/fix_benchmark_issues.py` (new)

## Benefits

1. **Better UX:** Users can now see paper titles directly in the leaderboard
2. **Quick Access:** Direct links to code repositories via GitHub icons
3. **Improved Visualization:** Line chart with dots makes trends clearer
4. **Flexible Filtering:** Users can select different metrics and sorting options
5. **Professional Design:** Matches PapersWithCode.com aesthetic
6. **Data Integrity:** API provides all necessary information without frontend workarounds

## No Breaking Changes

- All existing API endpoints remain backwards compatible
- New fields are optional and don't affect existing consumers
- Frontend gracefully handles missing paper_title or code_url values
