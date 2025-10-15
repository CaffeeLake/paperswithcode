# Evaluation Metrics Data Quality Guide

## Overview

This guide documents common data quality issues with evaluation metrics and how to prevent/fix them.

## Issue: Inconsistent Metric Naming

### Problem Description

The evaluation table stores metrics as JSONB data, which allows flexible metric names. However, inconsistent naming can cause display issues:

**Example Issue (Fixed):**
- Paper detail page showed: "64.8 AP" and "65.9 AP" ✓
- Benchmark leaderboard showed: "0 AP" and "65.9 AP" ✗

**Root Cause:**
- One evaluation used `"box mAP": "64.8"`
- Another used `"box AP": "65.9"`
- The benchmark page filtered/sorted by "box AP", causing the "box mAP" entry to show as 0

### Standard Metric Names

For **COCO (Common Objects in Context)** and similar object detection benchmarks, use these standard metric names:

| Metric | Standard Name | ❌ Avoid |
|--------|---------------|---------|
| Box Average Precision | `box AP` | box mAP, box_ap, bbox AP, bbox mAP |
| AP at IoU=0.50 | `AP50` | AP@50, AP@0.5, AP_50 |
| AP at IoU=0.75 | `AP75` | AP@75, AP@0.75, AP_75 |
| AP for small objects | `APS` | AP_small, AP-S |
| AP for medium objects | `APM` | AP_medium, AP-M |
| AP for large objects | `APL` | AP_large, AP-L |

### Validation Script

A validation script is available to check and fix metric naming inconsistencies:

```bash
# Check for issues (dry-run mode)
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py

# Fix issues
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py --fix
```

The script checks for:
1. **Metric naming inconsistencies** - Standardizes variations to canonical names
2. **Missing best_metric values** - Sets appropriate best_metric for each evaluation

### Manual Database Fixes

If you need to manually fix metric names in the database:

```sql
-- Example: Standardize "box mAP" to "box AP"
UPDATE evaluations
SET metrics = jsonb_set(
    jsonb_set(metrics, '{"box AP"}', metrics->'box mAP'),
    '{box mAP}', 'null'::jsonb
) - 'box mAP'
WHERE metrics ? 'box mAP';

-- Set best_metric for evaluations that don't have it
UPDATE evaluations
SET best_metric = 'box AP'
WHERE best_metric IS NULL
  AND metrics ? 'box AP';
```

## Best Practices for Data Import

### 1. Validate Metric Names Before Import

When importing evaluation data, validate metric names against the standard list:

```python
from typing import Dict

STANDARD_METRICS = {
    # Object Detection (COCO-style)
    'box AP': ['box mAP', 'box_ap', 'bbox AP', 'bbox mAP'],
    'AP50': ['AP@50', 'AP@0.5', 'AP_50'],
    'AP75': ['AP@75', 'AP@0.75', 'AP_75'],
    # Add more as needed
}

def standardize_metrics(metrics: Dict[str, any]) -> Dict[str, any]:
    """Standardize metric names to canonical form."""
    standardized = {}

    for metric_name, value in metrics.items():
        # Check if this is a known variation
        standard_name = metric_name
        for canonical, variations in STANDARD_METRICS.items():
            if metric_name in variations:
                standard_name = canonical
                break

        standardized[standard_name] = value

    return standardized
```

### 2. Set best_metric During Import

Always specify which metric is the primary/best metric for ranking:

```python
evaluation = {
    'model_name': 'Co-DETR',
    'metrics': {
        'box AP': '65.9',
        'AP50': '83.4',
        'Params (M)': '348'
    },
    'best_metric': 'box AP',  # ← Always set this!
    'best_rank': 1,  # Optional: set if known
}
```

### 3. Run Validation After Import

After importing new evaluation data, always run the validation script:

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py --fix
```

## Frontend Display Logic

The frontend pages display metrics differently:

### Paper Detail Page
- Displays **all available metrics** for each evaluation
- Shows metric key and value from the `metrics` JSONB field
- More forgiving of inconsistencies (shows what exists)

### Benchmark Leaderboard Page
- Filters/sorts by a **single selected metric** (usually `best_metric`)
- If the selected metric doesn't exist, displays 0 or N/A
- Requires consistent metric naming across all evaluations

## Database Schema

```sql
CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    task_id INTEGER REFERENCES tasks(id),
    dataset_id INTEGER REFERENCES datasets(id),
    model_name VARCHAR(255),
    methodology TEXT,
    metrics JSONB,                    -- Flexible metrics storage
    best_metric VARCHAR(100),         -- Name of primary metric for ranking
    best_rank INTEGER,                -- Rank based on best_metric
    uses_additional_data BOOLEAN DEFAULT FALSE,
    evaluated_on DATE,
    external_source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Troubleshooting

### Issue: Metrics show as 0 on leaderboard

**Diagnosis:**
```sql
-- Find evaluations with specific metric
SELECT id, model_name, metrics
FROM evaluations
WHERE dataset_id = YOUR_DATASET_ID;

-- Check what metric keys exist
SELECT DISTINCT jsonb_object_keys(metrics)
FROM evaluations
WHERE dataset_id = YOUR_DATASET_ID;
```

**Solution:**
1. Identify the inconsistent metric names
2. Run the validation script with `--fix`
3. Or manually update using SQL (see Manual Database Fixes above)

### Issue: Frontend shows different values for same paper

**Diagnosis:**
- Check if multiple evaluations exist for the same paper/model
- Verify metric names are consistent
- Check `best_metric` and `best_rank` values

**Solution:**
```sql
-- Find duplicate evaluations
SELECT paper_id, dataset_id, model_name, COUNT(*)
FROM evaluations
GROUP BY paper_id, dataset_id, model_name
HAVING COUNT(*) > 1;
```

## Regular Maintenance

### Weekly Checks

Run the validation script weekly to catch any new inconsistencies:

```bash
# Add to cron or scheduled task
0 2 * * 0 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py --fix
```

### Before Major Updates

Before deploying any changes that affect evaluation display:

1. Run validation script
2. Check a sample of papers on both pages:
   - Paper detail page: `/paper/ARXIV_ID`
   - Benchmark page: `/benchmark/DATASET_SLUG`
3. Verify metrics display consistently

## Related Files

- **Validation Script:** `backend/database/validate_evaluation_metrics.py`
- **Backend Service:** `backend/services/evaluation_service.py`
- **Frontend Components:**
  - Paper Detail: `frontend/src/pages/PaperDetail.tsx`
  - Benchmark: `frontend/src/pages/Benchmark.tsx`
- **API Endpoints:** `backend/routers/evaluations.py`

## Summary

✅ **Do:**
- Use standard metric names (see table above)
- Set `best_metric` for every evaluation
- Run validation script after imports
- Check both frontend pages after data changes

❌ **Don't:**
- Use metric name variations (box mAP vs box AP)
- Leave `best_metric` as NULL
- Import data without validation
- Assume frontend will handle inconsistencies
