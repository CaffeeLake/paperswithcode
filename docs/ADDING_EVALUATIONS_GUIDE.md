# Guide: Adding Evaluation Results

This guide explains how to properly add evaluation results to ensure they appear correctly on all relevant pages (paper detail, benchmark pages, and task pages).

## Overview

When you add an evaluation result, four things need to happen:
1. **Evaluation record** is created in the `evaluations` table
2. **Dataset-Task link** is created in the `task_datasets` junction table
3. **Metric direction** is verified in the `metrics` table (for correct ranking)
4. **Ranks are calculated** for the leaderboard

The system is designed to do this automatically, but this guide helps verify everything works correctly.

## Understanding Metrics and Ranking

The system supports two types of metrics:

### Higher is Better (Default)
Metrics where larger values indicate better performance:
- **AP, mAP, box AP** - Object detection metrics
- **Accuracy, Top-1 Accuracy, Top-5 Accuracy** - Classification metrics
- **F1, Precision, Recall** - Classification metrics
- **BLEU, ROUGE, METEOR** - Translation/summarization metrics
- **IoU, Dice, mIoU** - Segmentation metrics
- **AUC, NDCG, MRR** - Ranking metrics

For these metrics, rank 1 goes to the **highest** value.

### Lower is Better
Metrics where smaller values indicate better performance:
- **WER (Word Error Rate)** - Speech recognition
- **CER (Character Error Rate)** - Speech recognition, OCR
- **Perplexity** - Language models
- **Error Rate, Loss** - General error metrics
- **MAE, MSE, RMSE** - Regression metrics
- **FID** - Image generation quality

For these metrics, rank 1 goes to the **lowest** value.

### Adding New Metrics

If your evaluation uses a metric not in the database, add it to the `metrics` table:

```sql
INSERT INTO metrics (name, full_name, direction, description)
VALUES (
    'METEOR',
    'Metric for Evaluation of Translation with Explicit ORdering',
    'higher_is_better',
    'Machine translation evaluation metric'
);
```

Or using Python:

```python
from backend.models.database import Metric as DBMetric

metric = DBMetric(
    name="METEOR",
    full_name="Metric for Evaluation of Translation with Explicit ORdering",
    direction="higher_is_better",
    description="Machine translation evaluation metric"
)
db.add(metric)
db.commit()
```

**Note**: If a metric is not found in the `metrics` table, the system will default to "higher_is_better" and log a warning.

### Complete Metrics Reference

The database currently includes 37 predefined metrics. Here's a quick reference:

| Metric | Direction | Use Case |
|--------|-----------|----------|
| **WER** | Lower is better | Speech recognition |
| **CER** | Lower is better | Speech recognition, OCR |
| **Perplexity** | Lower is better | Language models |
| **Error Rate** | Lower is better | General errors |
| **Loss** | Lower is better | Training/validation |
| **MAE, MSE, RMSE** | Lower is better | Regression |
| **FID** | Lower is better | Image generation |
| **AP, mAP, box AP** | Higher is better | Object detection |
| **AP50, AP75, APS, APM, APL** | Higher is better | Object detection variations |
| **Accuracy** | Higher is better | Classification |
| **Top-1/Top-5 Accuracy** | Higher is better | Classification |
| **F1, Precision, Recall** | Higher is better | Classification |
| **AUC** | Higher is better | Binary classification |
| **BLEU, ROUGE, METEOR** | Higher is better | Translation/summarization |
| **IoU, Dice, mIoU** | Higher is better | Segmentation |
| **R@1, R@5, R@10** | Higher is better | Retrieval |
| **MRR, NDCG** | Higher is better | Ranking |
| **PSNR** | Higher is better | Image quality |

To see all metrics in the database:
```sql
SELECT name, full_name, direction
FROM metrics
ORDER BY direction, name;
```

## Method 1: Using the API (Recommended)

### Creating an Evaluation via API

```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 123,
    "task_id": 12,
    "dataset_id": 138,
    "model_name": "Whisper Large V2",
    "metrics": {"WER": "5.2"},
    "best_metric": "WER",
    "methodology": "Zero-shot automatic speech recognition"
  }'
```

The `EvaluationService.create_evaluation()` method automatically:
- ✓ Links the dataset to the task (if not already linked)
- ✓ Looks up the metric direction from the `metrics` table
- ✓ Calculates ranks for the leaderboard with correct sort order
- ✓ Returns the complete evaluation object

**Important**: Make sure the `best_metric` you specify exists in the `metrics` table with the correct direction. In the example above, WER is a "lower_is_better" metric, so lower values will rank higher.

### Frontend Integration

Use the evaluation form component (if available) or make API calls from your frontend:

```typescript
import { createEvaluation } from '@/lib/api';

const result = await createEvaluation({
  paper_id: 123,
  task_id: 12,
  dataset_id: 138,
  model_name: "Whisper Large V2",
  metrics: { WER: "5.2" },
  best_metric: "WER"
});
```

## Method 2: Bulk Import Scripts

When creating import scripts (in `backend/database/evaluations_setup/`), follow this pattern:

```python
from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
    TaskDataset,
    Metric as DBMetric,
)

def link_dataset_to_task(db: Session, task_id: int, dataset_id: int) -> bool:
    """
    Link a dataset to a task via the task_datasets junction table.
    """
    try:
        # Check if link already exists
        existing_link = (
            db.query(TaskDataset)
            .filter(
                TaskDataset.task_id == task_id,
                TaskDataset.dataset_id == dataset_id,
            )
            .first()
        )

        if existing_link:
            logger.debug(f"Dataset {dataset_id} already linked to task {task_id}")
            return True

        # Create the link
        task_dataset = TaskDataset(
            task_id=task_id,
            dataset_id=dataset_id
        )

        db.add(task_dataset)
        db.commit()

        logger.info(f"✓ Linked dataset {dataset_id} to task {task_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to link dataset to task: {e}")
        db.rollback()
        return False


def ensure_metric_exists(db: Session, metric_name: str, direction: str = "higher_is_better") -> bool:
    """
    Ensure a metric exists in the metrics table.

    Args:
        db: Database session
        metric_name: Name of the metric (e.g., "WER", "AP")
        direction: Either "higher_is_better" or "lower_is_better"
    """
    try:
        # Check if metric exists
        existing_metric = db.query(DBMetric).filter(
            DBMetric.name == metric_name
        ).first()

        if existing_metric:
            logger.debug(f"Metric '{metric_name}' already exists with direction '{existing_metric.direction}'")
            return True

        # Create the metric
        metric = DBMetric(
            name=metric_name,
            direction=direction,
            description=f"{metric_name} metric"
        )

        db.add(metric)
        db.commit()

        logger.info(f"✓ Created metric '{metric_name}' with direction '{direction}'")
        return True

    except Exception as e:
        logger.error(f"Failed to ensure metric exists: {e}")
        db.rollback()
        return False


def import_evaluation(db: Session, eval_data: dict):
    """Import a single evaluation."""

    # ... find paper, task, dataset ...

    # IMPORTANT: Link the dataset to the task BEFORE creating evaluation
    link_dataset_to_task(db, task.id, dataset.id)

    # IMPORTANT: Ensure metric exists with correct direction
    best_metric = eval_data.get("best_metric")
    if best_metric:
        # Example: WER is "lower_is_better", AP is "higher_is_better"
        metric_direction = "lower_is_better" if best_metric == "WER" else "higher_is_better"
        ensure_metric_exists(db, best_metric, metric_direction)

    # Create the evaluation
    evaluation = DBEvaluation(
        paper_id=paper.id,
        task_id=task.id,
        dataset_id=dataset.id,
        model_name=eval_data.get("model_name"),
        metrics=eval_data.get("metrics"),
        best_metric=best_metric,
        # ... other fields ...
    )

    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    return evaluation
```

## Verification Steps

After adding evaluations, verify they appear correctly:

### 1. Check the Database

```sql
-- Check evaluation was created
SELECT * FROM evaluations
WHERE paper_id = 123 AND dataset_id = 138;

-- Check dataset is linked to task
SELECT * FROM task_datasets
WHERE task_id = 12 AND dataset_id = 138;

-- Check metric direction is defined
SELECT name, direction, full_name
FROM metrics
WHERE name = 'WER';

-- Check for any unlinked pairs
SELECT DISTINCT
    e.task_id, t.name as task_name,
    e.dataset_id, d.name as dataset_name
FROM evaluations e
INNER JOIN tasks t ON e.task_id = t.id
INNER JOIN datasets d ON e.dataset_id = d.id
LEFT JOIN task_datasets td ON e.task_id = td.task_id AND e.dataset_id = td.dataset_id
WHERE td.task_id IS NULL;

-- Check for evaluations with undefined metrics
SELECT DISTINCT e.best_metric
FROM evaluations e
LEFT JOIN metrics m ON e.best_metric = m.name
WHERE e.best_metric IS NOT NULL
AND m.name IS NULL;
```

### 2. Test the API

```bash
# Get datasets for task (should include your dataset)
curl "http://localhost:8000/api/v1/datasets/?task=12"

# Get evaluations for paper
curl "http://localhost:8000/api/v1/papers/123/evaluations"

# Get evaluations for dataset
curl "http://localhost:8000/api/v1/datasets/138/evaluations"
```

### 3. Test the Frontend

1. **Paper detail page**: `http://localhost:8080/paper/{arxiv_id}`
   - Check "Benchmark Results" section shows the evaluation

2. **Benchmark page**: `http://localhost:8080/benchmark/{dataset_slug}`
   - Check the leaderboard includes your paper

3. **Task page**: `http://localhost:8080/tasks/{task_slug}`
   - Check "Leaderboards" section includes your dataset
   - This is where issues most commonly appear!

### 4. Run Verification Script

```bash
# Check for unlinked dataset-task pairs
uv run --env-file backend/keys.env python3 scripts/fix_unlinked_datasets.py
```

## Troubleshooting

### Dataset Not Showing on Task Page

**Symptom**: Evaluation appears on paper and benchmark pages, but dataset doesn't show in task's "Leaderboards" section.

**Cause**: Dataset is not linked to the task in `task_datasets` table.

**Solution**:
```bash
# Option 1: Run the fix script
uv run --env-file backend/keys.env python3 scripts/fix_unlinked_datasets.py

# Option 2: Manual SQL
psql -d paperswithcode_hf -c "
INSERT INTO task_datasets (task_id, dataset_id)
VALUES (12, 138)
ON CONFLICT DO NOTHING;
"
```

### Frontend Cache Issues

**Symptom**: Changes appear in API but not in frontend.

**Solution**:
- Hard refresh the browser (Ctrl+Shift+R / Cmd+Shift+R)
- Wait 5 minutes (TanStack Query cache TTL)
- Check browser console for API errors

### Ranks Not Calculated

**Symptom**: Evaluations exist but `best_rank` is NULL.

**Solution**: The API should automatically calculate ranks. If not:
```python
from backend.services.evaluation_service import EvaluationService
from backend.database.connection import db_manager

db = db_manager.session_local()
service = EvaluationService(db)
service.recalculate_ranks(task_id=12, dataset_id=138)
db.close()
```

### Incorrect Ranking Direction

**Symptom**: Rankings are reversed (e.g., higher WER values are ranked better than lower ones).

**Cause**: Metric direction not defined in `metrics` table or ranks calculated before metric was added.

**Solution**:

1. **Check if metric exists**:
```sql
SELECT name, direction FROM metrics WHERE name = 'WER';
```

2. **Add metric if missing**:
```sql
INSERT INTO metrics (name, full_name, direction, description)
VALUES (
    'WER',
    'Word Error Rate',
    'lower_is_better',
    'Word Error Rate - commonly used in speech recognition evaluation'
)
ON CONFLICT (name) DO NOTHING;
```

3. **Recalculate all ranks for that metric**:
```python
from backend.services.evaluation_service import EvaluationService
from backend.database.connection import db_manager
from sqlalchemy import text

db = db_manager.session_local()
service = EvaluationService(db)

# Find all leaderboards using this metric
result = db.execute(text("""
    SELECT DISTINCT task_id, dataset_id
    FROM evaluations
    WHERE best_metric = 'WER'
"""))

# Recalculate ranks for each leaderboard
for row in result:
    service.recalculate_ranks(task_id=row.task_id, dataset_id=row.dataset_id)
    print(f"✓ Recalculated ranks for task {row.task_id}, dataset {row.dataset_id}")

db.close()
```

## Related Files

- API Router: `backend/routers/evaluations.py`
- Service Layer: `backend/services/evaluation_service.py`
- Database Models: `backend/models/database.py`
- Metrics Migration: `backend/database/migration/create_metrics_table.sql`
- Import Scripts: `backend/database/evaluations_setup/`
- Verification Script: `scripts/fix_unlinked_datasets.py`
- Frontend Hook: `frontend/src/hooks/useDatasets.ts`
- Task Page: `frontend/src/pages/TaskDetail.tsx`
- Database Schema: `docs/DATABASE_SCHEMA_UML.md`

## Best Practices

1. **Always link datasets to tasks** when creating evaluations
2. **Verify metric direction** before adding evaluations with new metrics
3. **Check logs** for any errors during evaluation creation
4. **Run verification** after bulk imports
5. **Test all three pages** (paper, benchmark, task) after adding evaluations
6. **Check leaderboard rankings** to ensure correct sort order
7. **Document any manual fixes** so they can be automated later

## Future Improvements

- Add automatic repair on startup
- Add database constraint to prevent orphaned evaluations
- Add admin UI for managing dataset-task links
- Add monitoring/alerts for unlinked pairs
