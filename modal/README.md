# Modal Deployment for Evaluation Extraction

Deploy the evaluation extraction pipeline to [Modal](https://modal.com) for scalable processing of thousands of papers.

## Quick Start

```bash
# 1. Install Modal
pip install modal

# 2. Authenticate
modal token new

# 3. Create secret with your database credentials
# (see MODAL_SETUP.md for detailed instructions)

# 4. Test database connection
modal run modal/test_modal_db.py

# 5. Process a single paper
modal run modal/parse_modal.py --arxiv-id 2201.03545

# 6. Process a batch
modal run modal/parse_modal.py --batch modal/arxiv_ids_sample.txt
```

## Files

- **`parse_modal.py`** - Main Modal deployment script
- **`test_modal_db.py`** - Database connection test
- **`MODAL_SETUP.md`** - Complete setup and troubleshooting guide
- **`arxiv_ids_sample.txt`** - Sample batch file (add your ArXiv IDs here)

## Why Modal?

- **Scalable**: Process 100+ papers in parallel
- **Cost-effective**: ~$0.12 per paper, only pay for compute time
- **Simple**: No infrastructure to manage
- **Fast**: 1,000 papers in 1-2 hours vs days on a single machine

## Usage Examples

### Test with Skip Addition (No Database Changes)
```bash
modal run modal/parse_modal.py \
  --arxiv-id 2201.03545 \
  --skip-addition
```

### Small Batch (20 concurrent workers)
```bash
modal run modal/parse_modal.py \
  --batch modal/arxiv_ids_sample.txt \
  --max-workers 20
```

### Large Scale (100 concurrent workers)
```bash
modal run modal/parse_modal.py \
  --batch modal/my_large_batch.txt \
  --max-workers 100
```

## Cost Estimates

Based on Modal's pricing (as of 2024):

| Papers | Workers | Time | Estimated Cost |
|--------|---------|------|----------------|
| 10     | 5       | ~5 min | $1-2 |
| 100    | 20      | ~15 min | $10-15 |
| 1,000  | 50      | ~1-2 hrs | $100-150 |
| 10,000 | 100     | ~10-20 hrs | $1,000-1,500 |

Costs include:
- Compute (4GB RAM, 2 CPU)
- Network egress
- Assumes 30 seconds per paper average

## Performance Tips

1. **Start small**: Test with 10 papers first
2. **Use resume**: Cached results speed up re-runs
3. **Optimize workers**: More workers = faster but higher cost
4. **Monitor**: Check Modal dashboard for real-time costs
5. **Batch size**: Process 100-500 papers per batch for easier monitoring

## Troubleshooting

### Can't connect to database?

Run the test script:
```bash
modal run modal/test_modal_db.py
```

See `MODAL_SETUP.md` for detailed database configuration instructions.

### Function timing out?

Edit `parse_modal.py` and increase timeout:
```python
@app.function(
    timeout=1800,  # 30 minutes
)
```

### Out of memory?

Increase memory allocation:
```python
@app.function(
    memory=8192,  # 8GB
)
```

## Full Documentation

See **`MODAL_SETUP.md`** for:
- Detailed setup instructions
- PostgreSQL configuration
- Security considerations
- Performance tuning
- Advanced usage

## Support

- Modal Docs: https://modal.com/docs
- Modal Slack: https://modal.com/slack
- Project Issues: File an issue in this repository

## Local Alternative

For smaller batches or testing, you can run locally with GNU Parallel:

```bash
cat arxiv_ids.txt | parallel -j 2 \
  "uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id {} --resume"
```

This is free but much slower (2 papers at a time on your VPS).
