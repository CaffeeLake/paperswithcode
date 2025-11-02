# Leaderboard Triples Migration Guide

## Overview

This migration transforms the leaderboard system from dataset-level metrics to leaderboard-level (task, dataset, metric) triples. This allows:

- **Multiple leaderboards per task-dataset pair**: ImageNet can have separate leaderboards for Top-1 Accuracy, Top-5 Accuracy, and FID
- **Task-specific metrics**: Image Classification on ImageNet uses different metrics than Image Generation on ImageNet
- **Precise ranking**: Each triple has independent rankings

## Migration Steps

### 1. Create the new table

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migration/add_task_dataset_metrics_table.sql
```

This creates:
- `task_dataset_metrics` table with composite PK (task_id, dataset_id, metric_id)
- Indexes on task_id, dataset_id, metric_id, and (task_id, dataset_id)

### 2. Backfill data

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migration/migrate_dataset_metrics_to_triples.sql
```

This:
- Expands dataset_metrics × task_datasets into triples
- Adds triples implied by existing evaluations
- Creates composite index on evaluations(task_id, dataset_id, best_metric)
- Creates compatibility view `dataset_metrics_compat` for backward compatibility

### 3. Deploy code changes

The code changes are backward compatible. Deploy the updated backend:

**Files changed:**
- `backend/models/database.py` - Removed DatasetMetric, added TaskDatasetMetric
- `backend/services/leaderboard_metric_service.py` - New service for triple management
- `backend/services/evaluation_service.py` - Updated to rank per triple
- `backend/routers/datasets.py` - New endpoints for triple management, old endpoints deprecated

**New API endpoints:**
- `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`
- `POST /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`
- `PUT /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`
- `DELETE /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics/{metric_name}`

**Deprecated (but functional):**
- `GET /api/v1/datasets/{dataset_id}/metrics` - Returns metrics across all tasks

### 4. Verify migration

```bash
uv run --env-file backend/keys.env python backend/database/migration/verify_leaderboard_triples.py
```

This verifies:
- Triples are populated
- Evaluations have matching triples
- Ranks are calculated per triple
- Composite index exists

### 5. (Optional) Drop old table

After confirming everything works (wait at least one release cycle):

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migration/drop_dataset_metrics.sql
```

This drops:
- `dataset_metrics_compat` view
- `dataset_metrics` table
- Related indexes

## Key Concepts

### Leaderboard Triple

A leaderboard is defined by three components:
- **Task**: e.g., "Image Classification"
- **Dataset**: e.g., "ImageNet"
- **Metric**: e.g., "Top-1 Accuracy"

### Examples

**Before (dataset-level metrics):**
- ImageNet → [Top-1 Accuracy, Top-5 Accuracy, FID]
- All evaluations on ImageNet competed in the same ranking

**After (leaderboard triples):**
- (Image Classification, ImageNet, Top-1 Accuracy) - Separate leaderboard
- (Image Classification, ImageNet, Top-5 Accuracy) - Separate leaderboard
- (Image Generation, ImageNet, FID) - Separate leaderboard

Each has independent rankings!

### Ranking Behavior

**Old behavior:**
- All evaluations for (task, dataset) ranked together
- Only one leaderboard per task-dataset pair

**New behavior:**
- Evaluations ranked per (task, dataset, metric) triple
- Multiple leaderboards per task-dataset pair
- `recalculate_ranks(task_id, dataset_id, metric_name)` - Recalculates specific triple
- `recalculate_ranks(task_id, dataset_id)` - Recalculates all metrics for that pair

## API Usage Examples

### Get allowed metrics for a leaderboard

```bash
curl "http://localhost:8000/api/v1/datasets/6/tasks/12/metrics"
```

Response:
```json
{
  "task_id": "12",
  "dataset_id": "6",
  "task_name": "Object Detection",
  "dataset_name": "COCO",
  "metrics": [
    {
      "metric_id": "1",
      "metric_name": "AP",
      "metric_direction": "higher_is_better",
      "created_at": "2025-11-01T12:00:00Z"
    },
    {
      "metric_id": "2",
      "metric_name": "AP50",
      "metric_direction": "higher_is_better",
      "created_at": "2025-11-01T12:00:00Z"
    }
  ]
}
```

### Add a metric to a leaderboard

```bash
curl -X POST "http://localhost:8000/api/v1/datasets/6/tasks/12/metrics" \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "AP75"}'
```

### Set all metrics for a leaderboard

```bash
curl -X PUT "http://localhost:8000/api/v1/datasets/6/tasks/12/metrics" \
  -H "Content-Type: application/json" \
  -d '{"metric_names": ["AP", "AP50", "AP75", "APs", "APm", "APl"]}'
```

### Remove a metric from a leaderboard

```bash
curl -X DELETE "http://localhost:8000/api/v1/datasets/6/tasks/12/metrics/AP75"
```

## Backward Compatibility

### Old endpoints still work

The old `/datasets/{id}/metrics` endpoints are deprecated but functional:
- They aggregate metrics across all tasks linked to that dataset
- A deprecation warning is logged
- Update your code to use the new task-specific endpoints

### Validation behavior

- If no triples are configured for a leaderboard, all metrics are allowed (allow-all mode)
- This ensures existing evaluations continue to work during migration
- Configure triples to enforce metric restrictions

## Troubleshooting

### Evaluations without matching triples

If you see warnings about evaluations without matching triples:
1. This is OK if you haven't configured triples yet (allow-all mode)
2. To fix: Add the appropriate triples using the API or SQL

### Ranks not updating

If ranks aren't updating after creating/updating evaluations:
1. Check that the metric is in the metrics table
2. Verify the metric direction is correct
3. Manually trigger recalculation: Call `evaluation_service.recalculate_ranks(task_id, dataset_id, metric_name)`

### Performance issues

If queries are slow:
1. Verify indexes exist: Run verification script
2. Check query plans: Use `EXPLAIN ANALYZE`
3. Ensure composite index on evaluations exists

## Benefits

1. **Precise leaderboards**: Each metric gets its own ranking
2. **Flexibility**: Same dataset can be used for multiple tasks with different metrics
3. **Clarity**: Explicit definition of what constitutes a leaderboard
4. **Scalability**: Efficient indexes for triple-based queries
5. **Backward compatible**: Old code continues to work during migration

## Migration Checklist

- [ ] Create task_dataset_metrics table
- [ ] Backfill triples from dataset_metrics and evaluations
- [ ] Add composite index on evaluations
- [ ] Deploy updated code
- [ ] Verify migration with verification script
- [ ] Update API clients to use new endpoints
- [ ] Monitor for deprecation warnings
- [ ] (After 1+ release) Drop old dataset_metrics table

## Support

For questions or issues:
1. Check verification script output
2. Review migration SQL files
3. See DATABASE_SCHEMA_UML.md for schema details
4. Check API documentation at `/docs`
