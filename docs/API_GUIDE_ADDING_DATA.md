# API Guide: Adding Datasets and Evaluations

This guide provides quick reference for adding datasets and evaluation results to the PapersWithCode system.

## Quick Reference

| Endpoint | Purpose | Key Features |
|----------|---------|--------------|
| `POST /api/v1/datasets/` | Create datasets | Auto-generates slug, links to tasks |
| `POST /api/v1/evaluations/` | Add evaluation results | Auto-calculates ranks, links dataset to task |

## Adding Datasets

### Basic Example

```bash
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Video-MMLU",
    "full_name": "Video-MMLU: A Massive Multi-Discipline Lecture Understanding Benchmark",
    "description": "A comprehensive benchmark for evaluating Large Multimodal Models",
    "url": "https://enxinsong.com/Video-MMLU-web/",
    "hf_url": "https://huggingface.co/datasets/Enxin/Video-MMLU",
    "paper_url": "https://arxiv.org/abs/2504.14693",
    "task_ids": [9]
  }'
```

### Required Fields
- `name`: Dataset name (used to generate slug)
- `description`: Dataset description
- `url`: Dataset URL
- `hf_url`: Hugging Face dataset URL
- `paper_url`: URL to paper that introduced this dataset
- `task_ids`: Array of task IDs to link this dataset to

### Optional Fields
- `full_name`: Full dataset name
- `modalities`: Data types (e.g., ["Videos", "Text"])
- `languages`: Supported languages
- `license_name`: License name
- `introduced_date`: Introduction date (YYYY-MM-DD)

## Adding Evaluations

### Basic Example

```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 123,
    "task_id": 12,
    "dataset_id": 138,
    "model_name": "DETR-R50",
    "metrics": {"AP": "44.9", "AP50": "64.7"},
    "best_metric": "AP",
    "methodology": "End-to-End Object Detection with Transformers"
  }'
```

### Required Fields
- `paper_id`: Paper ID that produced this evaluation
- `task_id`: Task ID being evaluated
- `dataset_id`: Dataset ID used for evaluation
- `metrics`: Dictionary of metric names and values

### Optional Fields
- `model_name`: Name of the model/method used
- `methodology`: Methodology description
- `best_metric`: Name of the primary metric for ranking
- `best_rank`: Best rank achieved
- `uses_additional_data`: Whether additional data was used (default: false)
- `evaluated_on`: Evaluation date (YYYY-MM-DD)
- `external_source_url`: URL to external source

## Common Patterns

### 1. Dataset with Multiple Tasks
```json
{
  "name": "COCO",
  "task_ids": [1, 2, 3],  // Object Detection, Instance Segmentation, etc.
  "description": "Common Objects in Context dataset"
}
```

### 2. Evaluation with Multiple Metrics
```json
{
  "paper_id": 123,
  "task_id": 1,
  "dataset_id": 5,
  "metrics": {
    "AP": "44.9",
    "AP50": "64.7",
    "AP75": "49.0"
  },
  "best_metric": "AP"
}
```

### 3. Speech Recognition Evaluation (Lower is Better)
```json
{
  "paper_id": 456,
  "task_id": 8,
  "dataset_id": 12,
  "metrics": {"WER": "5.2"},
  "best_metric": "WER"
}
```

## Error Handling

### Common Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 400 | Invalid request data | Check required fields and data types |
| 404 | Task/Dataset not found | Verify task_ids and dataset_id exist |
| 409 | Dataset slug already exists | Use different name or update existing |
| 500 | Server error | Check server logs for details |

### Validation Tips

**Datasets:**
- Ensure all `task_ids` exist in the database
- Use descriptive names that will generate good slugs
- Provide complete URLs (http/https)

**Evaluations:**
- Verify `paper_id`, `task_id`, and `dataset_id` exist
- Use metric names that exist in the `metrics` table
- For "lower is better" metrics (WER, error rates), ensure they're defined in the metrics table

## Best Practices

1. **Link datasets to relevant tasks** - This ensures they appear in task leaderboards
2. **Use consistent metric names** - Check existing metrics in the database
3. **Provide complete metadata** - URLs, descriptions, and methodology help users
4. **Test with small examples first** - Verify the API works before bulk operations

## Verification

After adding data, verify it appears correctly:

```bash
# Check dataset was created
curl "http://localhost:8000/api/v1/datasets/?name=Video-MMLU"

# Check evaluation was created
curl "http://localhost:8000/api/v1/evaluations/?paper_id=123"

# Check dataset appears in task leaderboard
curl "http://localhost:8000/api/v1/datasets/?task=9"
```

## Related Documentation

- [Adding Evaluations Guide](ADDING_EVALUATIONS_GUIDE.md) - Detailed evaluation guide
- [API Expansion Plan](API_EXPANSION_PLAN.md) - Complete API roadmap
- [Database Schema](DATABASE_SCHEMA_UML.md) - Database structure reference
