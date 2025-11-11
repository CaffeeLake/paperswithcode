# Dataset-Task Consistency in Evaluations

## Problem

Prior to this fix, evaluations (leaderboard results) could be created with inconsistent task-dataset pairings. For example, the same dataset could be used with different tasks across different papers, fragmenting leaderboards and making comparisons difficult.

### Example Issues Found

1. **LVBench** - Used with both "Vision-Language Models" and "Video-Language Models" tasks
2. **OCRBench** - Used with both "Vision-Language Models" and "OCR" tasks
3. **LIBERO** - Used with both "Vision-Language Models" and "Robotics" tasks

## Solution

### 1. Data Cleanup

Fixed all existing inconsistencies in the database:

- **OCRBench** (ID: 155): Moved 3 evaluations from "Vision-Language Models" → "OCR"
- **LVBench** (ID: 58): Moved 1 evaluation from "Vision-Language Models" → "Video-Language Models"
- **LIBERO** (ID: 108): Moved 1 evaluation from "Vision-Language Models" → "Robotics"

### 2. Validation Implementation

Added automatic validation in `backend/services/evaluation_service.py`:

#### New Method: `_validate_dataset_task_consistency()`

This method enforces consistency rules:

**For single-task datasets (most common):**
- Evaluations MUST use the officially linked task
- Example: LVBench evaluations must use "Video-Language Models"

**For multi-task datasets (exceptions):**
- Evaluations can use ANY of the officially linked tasks
- Example: ETH3D can use either "Depth estimation" or "3D Understanding"

**For new datasets (not yet linked):**
- Any task is allowed (temporary grace period)
- Once a dataset is linked to a task, consistency is enforced

#### Integration Points

Validation is called in:
1. `create_evaluation()` - Before creating new evaluations
2. `update_evaluation()` - Before updating task or dataset fields

If validation fails, a clear error message is returned:
```
Task mismatch for dataset 'LVBench'. This dataset is officially linked to
task 'Video-Language Models' but you're trying to use task 'Vision-Language Models'.
Please use the correct task to maintain consistent leaderboards.
```

### 3. Scripts Created

#### Detection Script: `scripts/find_dataset_task_inconsistencies.py`

Analyzes all evaluations and reports:
- Datasets with inconsistent task usage
- Distinction between legitimate multi-task datasets and problematic cases
- Total evaluation counts and impact

Usage:
```bash
uv run --env-file backend/keys.env python scripts/find_dataset_task_inconsistencies.py
```

#### Fix Script: `scripts/fix_dataset_task_inconsistencies.py`

Provides detailed reports and fixes:
- Shows which specific papers/evaluations have incorrect tasks
- Supports dry-run mode for verification
- Allows targeted fixes with command-line arguments

Usage:
```bash
# View detailed report
uv run --env-file backend/keys.env python scripts/fix_dataset_task_inconsistencies.py

# Fix specific dataset
uv run --env-file backend/keys.env python scripts/fix_dataset_task_inconsistencies.py \
  --fix --dataset 58 --from-task 8 --to-task 9
```

#### Test Script: `scripts/test_evaluation_validation.py`

Comprehensive test suite that verifies:
- Incorrect tasks are blocked
- Correct tasks are allowed
- Multi-task datasets work properly
- Error messages are helpful

Usage:
```bash
uv run --env-file backend/keys.env python scripts/test_evaluation_validation.py
```

## Results

### Before Fix
- 3 datasets with inconsistent task usage
- 5 evaluations using wrong tasks
- Fragmented leaderboards

### After Fix
- 0 problematic inconsistencies
- 1 legitimate multi-task dataset (ETH3D)
- All leaderboards now consistent
- Future inconsistencies prevented by validation

## How to Add Multi-Task Datasets

If a dataset should legitimately support multiple tasks (like ImageNet for both image classification and generation), add entries to the `task_datasets` table:

```sql
INSERT INTO task_datasets (task_id, dataset_id) VALUES
  (1, 123),  -- Task 1
  (2, 123);  -- Task 2
```

The validation will automatically recognize this as a multi-task dataset and allow evaluations with any of these tasks.

## API Impact

### For Evaluation Creation

When creating evaluations via the API, ensure the task matches the dataset's officially linked task:

```bash
# This will succeed
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 123,
    "task_id": 9,        # Video-Language Models
    "dataset_id": 58,    # LVBench
    "metrics": {"Accuracy": "51.07"}
  }'

# This will fail with validation error
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 123,
    "task_id": 8,        # Vision-Language Models (WRONG!)
    "dataset_id": 58,    # LVBench
    "metrics": {"Accuracy": "51.07"}
  }'
```

### Error Response

When validation fails, the API returns a 400 Bad Request with a clear error message:

```json
{
  "detail": "Task mismatch for dataset 'LVBench'. This dataset is officially linked to task 'Video-Language Models' but you're trying to use task 'Vision-Language Models'. Please use the correct task to maintain consistent leaderboards."
}
```

## Future Considerations

1. **Dataset-Task Associations**: When adding new datasets, ensure they are properly linked to their primary task(s) in the `task_datasets` table

2. **Bulk Data Import**: Scripts that import large amounts of evaluation data should validate task-dataset consistency before insertion

3. **Migration Scripts**: If large-scale task reorganization is needed in the future, create migration scripts similar to `fix_dataset_task_inconsistencies.py`

## Monitoring

Run the detection script periodically to ensure consistency:

```bash
# Add to cron or run manually
uv run --env-file backend/keys.env python scripts/find_dataset_task_inconsistencies.py
```

Exit code 0 means all clear, exit code 1 means inconsistencies detected.
