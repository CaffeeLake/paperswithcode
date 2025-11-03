# Step 5 Alignment with Leaderboard Triple Design

## Summary

Updated `extract_evaluation_results/step_5.py` to fully align with the database schema's leaderboard triple design, where leaderboards are defined by **(task, dataset, metric)** triples rather than just (task, dataset) pairs.

## Database Schema Context

### Leaderboard Triples

The database schema (as documented in `docs/DATABASE_SCHEMA_UML.md`) defines leaderboards using the `task_dataset_metrics` table:

```sql
CREATE TABLE task_dataset_metrics (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    metric_id BIGINT NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id, dataset_id, metric_id)
);
```

### Key Concepts

1. **Datasets** can serve multiple tasks (e.g., ImageNet-1k for both Image Classification and Image Generation)
2. **Tasks** define the problem being measured (e.g., Image Classification, Object Detection)
3. **Metrics** define how performance is scored with direction (higher/lower is better)
4. **Evaluations** belong to a specific triple via the `best_metric` field

### Example Triples

- (Image Classification, ImageNet-1k, Top-1 Accuracy)
- (Image Classification, ImageNet-1k, Top-5 Accuracy)
- (Image Generation, ImageNet-1k, FID)
- (Object Detection, COCO, AP)
- (Object Detection, COCO, AP50)

## Changes Implemented

### 1. Enhanced Duplicate Detection (✅ Completed)

**Before**: Duplicate check only considered `(paper_id, task_id, dataset_id, model_name)`

**After**: Duplicate check now includes `best_metric` in the key:

```python
existing = (
    session.query(DBEvaluation)
    .filter(
        DBEvaluation.paper_id == paper_id,
        DBEvaluation.task_id == task_id,
        DBEvaluation.dataset_id == dataset_id,
        DBEvaluation.model_name == model_name,
        DBEvaluation.best_metric == normalized_best_metric,  # NEW
    )
    .first()
)
```

**Benefit**: Allows the same model to have separate evaluation records for different metrics on the same dataset (e.g., one for AP, one for AP50).

### 2. Metric Validation and Normalization (✅ Completed)

**Added validation logic**:

```python
# Case-insensitive lookup of metric in metrics table
metric_def = (
    session.query(DBMetric)
    .filter(DBMetric.name.ilike(best_metric))
    .first()
)

if not metric_def:
    return f"Error: Metric '{best_metric}' not found in metrics table..."

# Use the canonical name from the database
normalized_best_metric = metric_def.name
```

**Benefits**:
- Ensures `best_metric` is a valid metric from the `metrics` table
- Normalizes metric names (case-insensitive matching)
- Provides clear error messages when invalid metrics are used
- Verifies `best_metric` exists in the metrics dictionary

### 3. Triple Validation via Service Layer (✅ Completed)

**Existing validation** in `EvaluationService.create_evaluation()`:

```python
# Validate metrics against leaderboard's allowed metrics
metric_service = LeaderboardMetricService(self.db)
is_valid, error_message = metric_service.validate_metrics_for_leaderboard(
    task_id, dataset_id, metric_keys, best_metric
)

if not is_valid:
    raise ValueError(error_message)
```

The `LeaderboardMetricService.validate_metrics_for_leaderboard()` method:
- Queries `task_dataset_metrics` to get allowed metrics for the (task, dataset) pair
- Validates that `best_metric` is in the allowed set
- Returns clear error messages if validation fails
- Supports backwards compatibility (allows all metrics if no restrictions configured)

**Note**: This validation was already present in the service layer. The changes in step_5.py ensure proper preparation before calling the service.

### 4. New Helper Tool: `get_leaderboard_metrics` (✅ Completed)

**Added new tool** to help the AI agent discover valid metrics:

```python
@function_tool
async def get_leaderboard_metrics(task_id: int, dataset_id: int) -> str:
    """Get the list of allowed metrics for a specific leaderboard (task + dataset).

    This tool helps you determine which metrics are valid for a given (task, dataset) pair.
    Each (task, dataset, metric) triple defines a unique leaderboard.
    """
```

**Benefits**:
- Agent can query which metrics are valid before attempting to add an evaluation
- Provides clear information about metric directions (higher/lower is better)
- Helps prevent validation errors by checking constraints upfront

### 5. Updated Agent Prompt (✅ Completed)

**Enhanced the agent instructions** to explain:
- Leaderboards as (task, dataset, metric) triples
- How the same dataset can serve multiple tasks
- How the same task-dataset pair can have multiple leaderboards with different metrics
- The importance of `best_metric` for proper leaderboard placement
- How to use the new `get_leaderboard_metrics` tool

**Key sections added**:

```
## CRITICAL: Understanding Leaderboards as Triples

Leaderboards are defined by **(task, dataset, metric)** triples. For example:
- (Image Classification, ImageNet-1k, Top-1 Accuracy)
- (Image Classification, ImageNet-1k, Top-5 Accuracy)
- (Image Generation, ImageNet-1k, FID)
```

```
## Checking Valid Metrics for a Leaderboard

Before adding an evaluation, you can use the get_leaderboard_metrics tool to check which metrics are allowed
for a specific (task, dataset) pair. This helps you choose the correct best_metric value.
```

### 6. Updated Tool Documentation (✅ Completed)

**Enhanced `add_evaluation_result` docstring**:
- Clarified that evaluations are ranked on the (task, dataset, metric) triple
- Emphasized that `best_metric` must be valid for the leaderboard
- Explained that `best_metric` determines which leaderboard triple the evaluation belongs to

## Testing Recommendations

To verify the implementation works correctly:

1. **Test duplicate prevention with different metrics**:
   ```python
   # Should succeed: Same model, same dataset, different metrics
   add_evaluation_result(paper_id=1, task_id=2, dataset_id=3,
                        model_name="DETR", metrics={"AP": "44.9"}, best_metric="AP")
   add_evaluation_result(paper_id=1, task_id=2, dataset_id=3,
                        model_name="DETR", metrics={"AP50": "64.7"}, best_metric="AP50")

   # Should fail: Duplicate triple
   add_evaluation_result(paper_id=1, task_id=2, dataset_id=3,
                        model_name="DETR", metrics={"AP": "45.0"}, best_metric="AP")
   ```

2. **Test metric validation**:
   ```python
   # Should fail: Invalid metric name
   add_evaluation_result(..., best_metric="InvalidMetric")

   # Should succeed: Valid metric (case-insensitive)
   add_evaluation_result(..., best_metric="ap")  # normalized to "AP"
   ```

3. **Test triple validation**:
   ```python
   # Should fail if (task, dataset, metric) triple not in task_dataset_metrics
   add_evaluation_result(task_id=1, dataset_id=2, best_metric="WER")
   # (if WER is not a valid metric for that task-dataset pair)
   ```

4. **Test leaderboard metrics query**:
   ```python
   # Should list allowed metrics for a leaderboard
   get_leaderboard_metrics(task_id=2, dataset_id=72)
   ```

## Backwards Compatibility

The implementation maintains backwards compatibility:

1. **Metric restrictions are optional**: If no metrics are configured in `task_dataset_metrics` for a leaderboard, all metrics are allowed (backwards compatibility mode)

2. **Service layer handles validation**: The existing `EvaluationService` already validates triples, so existing code continues to work

3. **Clear error messages**: When validation fails, users get actionable error messages explaining what went wrong

## Architecture Excellence

The implementation achieves excellent separation of concerns:

1. **step_5.py (Agent Layer)**:
   - Normalizes metric names
   - Checks for duplicates including best_metric
   - Provides clear error messages
   - Offers helper tools for discovery

2. **EvaluationService (Service Layer)**:
   - Validates triples against task_dataset_metrics
   - Handles database transactions
   - Recalculates ranks per triple
   - Maintains data integrity

3. **LeaderboardMetricService (Service Layer)**:
   - Manages task_dataset_metrics relationships
   - Validates metrics for leaderboards
   - Provides triple management API

This layered approach ensures that:
- Business logic stays in the service layer
- Agent tools focus on user interaction and validation
- Database constraints are enforced consistently
- The system is maintainable and testable

## Conclusion

The `step_5.py` agent now fully reflects the leaderboard triple design:

✅ Duplicate detection includes `best_metric` in the key
✅ Metric validation ensures valid, normalized metric names
✅ Triple validation happens via the service layer
✅ New tool helps discover valid metrics for leaderboards
✅ Agent prompt explains the triple concept clearly
✅ Backwards compatibility maintained

The agent can now correctly submit evaluation results to leaderboards defined by (task, dataset, metric) triples, allowing the same dataset to serve multiple tasks and the same task-dataset pair to have multiple leaderboards with different metrics.
