# Dataset Enrichment Guide

This guide explains how to enrich existing datasets in the database with missing information using the new dataset enrichment workflow.

## Overview

We identified **91 datasets** with evaluations that are missing key information:
- **3 datasets** missing descriptions
- **61 datasets** missing paper URLs
- **55 datasets** missing Hugging Face URLs

The new enrichment workflow uses AI-powered web search to automatically find and add this missing information.

## What's New

### 1. New Tool: `update_dataset()`

Added to `extract_evaluation_results/tools.py`:

```python
async def update_dataset(
    dataset_id: int,
    description: str | None = None,
    full_name: str | None = None,
    url: str | None = None,
    hf_url: str | None = None,
    paper_url: str | None = None,
) -> str
```

This tool allows agents to update existing datasets with new information (only provided fields are updated).

### 2. New Script: `find_datasets_missing_info.py`

Located at `/root/python_projects/paperswithcode/find_datasets_missing_info.py`

Identifies datasets with evaluations that have missing information:

```bash
uv run --env-file backend/keys.env python find_datasets_missing_info.py
```

**Output:** List of 91 datasets ordered by evaluation count, showing which fields are missing (✓/✗ for description, paper URL, HF URL).

### 3. New Enrichment Script: `enrich_datasets.py`

Located at `extract_evaluation_results/enrich_datasets.py`

This script:
1. Identifies datasets with missing information
2. Uses AI-powered web search (via Exa AI MCP) to find missing data
3. Updates datasets in the database

## Usage

### Command Options

```bash
--dataset_ids ID [ID ...]   # Specific dataset IDs to enrich
--limit N                    # Limit to top N datasets by eval count
--apply                      # Actually update DB (default is dry-run)
--batch-size N               # Concurrent datasets per batch (default: 3)
```

**IMPORTANT - Memory Management:**
- Default batch size: 3 (recommended for 4GB RAM VPS)
- Each concurrent dataset uses ~100-150MB RAM
- Adjust `--batch-size` based on available memory:
  - 2GB RAM: use `--batch-size 1`
  - 4GB RAM: use `--batch-size 2-3` (default: 3)
  - 8GB+ RAM: use `--batch-size 5-10`

### Dry-Run Mode (Default - Safe)

Test the enrichment without making any actual updates:

```bash
# Enrich a specific dataset (MMMU, ID 31)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 31

# Enrich top 10 datasets by evaluation count (in batches of 3)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10

# Enrich multiple specific datasets with batch size 2 (lower memory)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 31 33 74 --batch-size 2
```

**Example Output:**
```
DRY RUN MODE - No actual updates will be made
Use --apply flag to actually update the database
================================================================================

Found 1 dataset(s) to enrich:
1. MMMU (ID: 31) - Missing: description, paper_url

Enriching dataset: MMMU (ID: 31)
  Missing fields: description, paper_url
  Found information for: description, paper_url
  [DRY RUN] Would update with: {
  "description": "MMMU (A Massive Multi-discipline Multimodal Understanding and Reasoning Benchmark...)",
  "paper_url": "https://arxiv.org/abs/2311.16502"
}

ENRICHMENT SUMMARY
================================================================================
Successfully enriched: 1/1 datasets

[DRY RUN] No actual updates were made. Use --apply to update the database.
```

### Apply Mode (Actually Update Database)

Once you've verified the dry-run results, add the `--apply` flag to actually update:

```bash
# Apply updates to a single dataset
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 31 --apply

# Apply updates to top 10 datasets (processes in batches of 3)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10 --apply

# Apply updates to top 20 datasets with lower memory usage (batches of 2)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 20 --batch-size 2 --apply

# Apply updates to ALL remaining datasets (will take time, processes safely in batches)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --apply
```

**Example Output with Batch Processing:**
```
Processing in batches of 3 to manage memory usage
================================================================================

--- Batch 1/3 (datasets 1-3) ---
Enriching dataset: AI2D (ID: 33)
Enriching dataset: ETH3D (ID: 218)
Enriching dataset: ChartQA (ID: 30)
  ✓ Successfully updated dataset: ID=33, Name=AI2D
  ✓ Successfully updated dataset: ID=218, Name=ETH3D
  ✓ Successfully updated dataset: ID=30, Name=ChartQA
Batch 1 completed: 3/3 successful
Waiting 3 seconds for memory cleanup before next batch...

--- Batch 2/3 (datasets 4-6) ---
...
```

## How It Works

### Step-by-Step Process

1. **Identification Phase**
   - Queries the database for datasets with evaluations
   - Identifies which fields are missing (description, paper_url, hf_url)
   - Orders by evaluation count (most important datasets first)

2. **Information Gathering Phase (Batched Parallel Processing)**
   - Processes datasets in configurable batches (default: 3 concurrent datasets)
   - Within each batch, datasets are processed in parallel for efficiency
   - For each dataset, creates an AI agent with:
     - Access to Exa AI web search (for general information)
     - Access to Hugging Face MCP (for HF-specific data)
     - Context about which fields are missing
     - Existing dataset information
   - Multiple agents run concurrently within each batch
   - 3-second delay between batches for memory cleanup
   - **Memory-safe**: Prevents OOM on 4GB RAM VPS

3. **Agent Search Strategy**
   - Performs 2-3 focused web searches per dataset
   - Looks for official sources (ArXiv, conference papers, HF)
   - Prioritizes finding the most critical missing fields
   - Maximum 15 turns to stay efficient

4. **Update Phase**
   - Validates gathered information
   - Only updates fields that were originally missing
   - Uses the backend service directly for database updates
   - Provides detailed feedback on what was updated
   - Updates happen in parallel for all datasets

## Recommended Workflow

### Phase 1: High-Impact Datasets (Top 20)

Start with the most important datasets (those with the most evaluations):

```bash
# 1. Dry-run on top 20
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 20

# 2. Review the output carefully

# 3. If everything looks good, apply (will process in ~7 batches of 3)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 20 --apply

# Optional: Use smaller batches if you notice memory issues
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 20 --batch-size 2 --apply
```

**Top datasets by evaluation count:**
1. COCO val2017 (33 evaluations) - missing paper_url, hf_url
2. LibriSpeech Clean (22 evaluations) - missing paper_url, hf_url
3. LibriSpeech Other (21 evaluations) - missing paper_url, hf_url
4. ADE20K (20 evaluations) - missing paper_url
5. Tedlium (18 evaluations) - missing paper_url

### Phase 2: Batch Processing

Process the remaining datasets in batches:

```bash
# Process next 30 datasets
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 30 --apply

# Or continue with all remaining
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --apply
```

### Phase 3: Specific Fixes

For datasets that failed or need special attention:

```bash
# Target specific dataset IDs
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 74 --apply
```

## Integration with Existing Workflow

The enrichment script complements the existing evaluation extraction workflow:

### Existing Workflow (Adding New Datasets)
- `step_1.py` - Extract dataset mentions from papers
- `step_2.py` - Check if datasets exist in DB
- `step_3.py` - Gather info about NEW datasets (not in DB)
- `step_4.py` - ADD new datasets to DB

### New Enrichment Workflow (Updating Existing Datasets)
- `find_datasets_missing_info.py` - Identify datasets needing enrichment
- `enrich_datasets.py` - Gather info and UPDATE existing datasets

**Key Difference:**
- `step_3.py` + `step_4.py` = Add NEW datasets
- `enrich_datasets.py` = Update EXISTING datasets

Both use similar AI-powered information gathering but serve different purposes.

## Technical Details

### Architecture

```
enrich_datasets.py
├── get_datasets_missing_info()        # DB query for datasets needing enrichment
├── EnrichDatasetStep                  # AI agent for gathering information
│   ├── Tools: [find_dataset, get_tasks_by_area]
│   ├── MCP Servers: [exa, huggingface]
│   └── Model: gpt-5-mini
├── enrich_single_dataset()            # Process one dataset
│   ├── Run agent to gather info
│   ├── Validate gathered data
│   └── Update dataset via backend service (DatasetService)
└── main()                             # Batched parallel execution
    ├── Split datasets into batches (default: 3 per batch)
    ├── For each batch:
    │   ├── asyncio.gather(*tasks)     # Process batch datasets concurrently
    │   ├── Show batch progress
    │   └── await asyncio.sleep(3)     # Memory cleanup delay
    └── Aggregate results
```

**Key Features:**
- **Batched Processing**: Processes datasets in configurable batches (default: 3)
- **Memory-Safe**: Prevents OOM on 4GB RAM VPS by limiting concurrent agents
- **Progress Tracking**: Shows per-batch and overall progress
- **Direct Service Calls**: Uses `DatasetService` directly instead of tool wrappers
- **Robust Error Handling**: Exceptions in one dataset don't affect others
- **MCP Server Management**: Each agent manages its own MCP server lifecycle
- **Auto Cleanup**: 3-second delay between batches for garbage collection

### MCP Server Requirements

- **Exa AI MCP**: Required for web search
- **Hugging Face MCP**: Optional (requires `HF_TOKEN` in `backend/keys.env`)

### API Endpoints Used

- `PUT /api/v1/datasets/{dataset_id}` - Updates dataset fields
- Backend service: `DatasetService.update_dataset()`

## Success Metrics

### Expected Results

After running enrichment on all 91 datasets:
- Reduced missing descriptions from 3 to ~0
- Reduced missing paper URLs from 61 to ~10-20 (some may not have papers)
- Reduced missing HF URLs from 55 to ~20-30 (not all datasets are on HF)

### Typical Success Rate
- ~90-95% success rate for finding paper URLs (for recent datasets)
- ~70-80% success rate for finding HF URLs (depends on dataset)
- ~95%+ success rate for finding/improving descriptions

## Troubleshooting

### Out of Memory (OOM) Issues

**Symptom:** Script crashes or system becomes unresponsive during enrichment

**Cause:** Too many concurrent agents consuming memory

**Solutions:**
1. **Reduce batch size**:
   ```bash
   # Use smaller batches
   uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10 --batch-size 2 --apply

   # For very constrained systems (2GB RAM)
   uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10 --batch-size 1 --apply
   ```

2. **Check available memory**:
   ```bash
   free -h  # Check available RAM
   ```

3. **Process in smaller chunks**:
   ```bash
   # Process 5 at a time with batch size 2
   uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 5 --batch-size 2 --apply
   ```

**Memory Guidelines:**
- Each concurrent dataset uses ~100-150MB RAM
- Batch size 3 = ~300-450MB RAM needed
- Always leave 500MB+ free for system operations

### Agent Fails to Find Information

**Symptom:** Agent returns no new information

**Possible causes:**
1. Dataset is very old/obscure
2. No online presence
3. Wrong dataset name in database

**Solution:**
- Try updating the dataset name manually first
- Add information manually via API if you know the correct URLs

### Rate Limiting

**Symptom:** Slow performance or errors about rate limits

**Solution:**
- Process in smaller batches (use `--limit`)
- The script already includes 3-second delays between batches

### Agent Timeout

**Symptom:** Agent takes too long (>15 turns)

**Solution:**
- The agent has a 15-turn limit built-in
- Should automatically complete or fail gracefully

## Examples

### Example 1: Enrich MMMU Dataset

```bash
$ uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 31

# Output shows:
# - Missing: description, paper_url
# - Found description: "MMMU (A Massive Multi-discipline Multimodal Understanding...)"
# - Found paper_url: "https://arxiv.org/abs/2311.16502"
```

### Example 2: Batch Enrich Top 10 Datasets

```bash
$ uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10 --apply

# Processes:
# 1. COCO val2017 (33 evals)
# 2. LibriSpeech Clean (22 evals)
# ... (top 10 by eval count)
#
# Summary shows: "Successfully enriched: 9/10 datasets"
```

## Monitoring

### Check Results

After running enrichment, verify the updates:

```bash
# Check a specific dataset via API
curl "http://localhost:8000/api/v1/datasets/31"

# Or re-run the finder script
uv run --env-file backend/keys.env python find_datasets_missing_info.py
```

### Logs

Agent activity is logged with timestamps and tool calls. Check console output for:
- Which web searches were performed
- What information was found
- Any errors encountered

## Future Improvements

Potential enhancements:
1. Add support for updating `url` (main dataset website)
2. Add support for finding additional metadata (license, size, etc.)
3. Batch API calls for better performance
4. Retry logic for failed enrichments
5. Store enrichment history/audit trail

## Summary

You now have a complete workflow to:
1. ✅ Identify datasets missing information (`find_datasets_missing_info.py`)
2. ✅ Automatically gather missing data using AI (`enrich_datasets.py`)
3. ✅ Update existing datasets safely (dry-run by default)
4. ✅ Integrate with existing evaluation extraction workflow

**Next Steps:**
1. Start with a dry-run on top 10-20 datasets
2. Review the results
3. Apply updates if results look good
4. Continue with remaining datasets in batches
5. Manually review any failed enrichments
