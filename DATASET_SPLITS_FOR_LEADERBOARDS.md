# Dataset Splits for Separate Leaderboards - Implementation Complete ✅

## Overview

Successfully implemented separate leaderboards for dataset splits (like COCO test-dev, COCO minival, etc.), matching the legacy PapersWithCode behavior shown in the screenshot. Each split now has its own independent leaderboard with different results.

## What Was Implemented

### 1. Dataset Hierarchy System ✅
- Added `variant_type`, `split_name`, `introduced_year`, `paper_url` to datasets table
- Created parent-child relationships between datasets and their splits
- Populated COCO with 6 splits and 5 major variants (12 total entries)

### 2. Smart Dataset Matching Utility ✅
Created `backend/utils/dataset_utils.py` with:
- `find_dataset_by_name()` - Intelligently matches legacy dataset names to correct splits
  - "COCO test-dev" → finds split with `split_name='test-dev'`
  - "COCO minival" → finds split with `split_name='minival'`
  - Handles fuzzy matching for variations in naming
- `get_or_create_dataset_split()` - Dynamically creates splits as needed
- `get_dataset_with_splits()` - Retrieves dataset with all its children

### 3. Evaluation Migration ✅
Created `backend/database/evaluations_setup/migrate_evaluations_to_splits.py`:
- Migrated 3 existing evaluations from parent COCO to correct splits:
  - **DETR-DC5** (ResNet-101) → COCO minival
  - **Co-DETR** (Swin-L) → COCO test-dev
  - **Co-DETR** → COCO test-dev
- Loads 13,173 paper-to-dataset mappings from legacy evaluation-tables.json
- Automatically determines correct split based on legacy data

### 4. Updated API Models ✅
Updated `backend/services/dataset_service.py`:
- Added `variant_type`, `split_name`, `introduced_year`, `paper_url` to API responses
- All dataset endpoints now return split information
- Splits appear as separate datasets in listings

## Current Database State

### Datasets
```
┌─────────────────────┬──────────────┬────────────┬──────┐
│ Name                │ Variant Type │ Split Name │ ID   │
├─────────────────────┼──────────────┼────────────┼──────┤
│ COCO                │ NULL         │ NULL       │ 1    │
│ ├─ COCO test-dev    │ split        │ test-dev   │ 2    │
│ ├─ COCO test-chal.. │ split        │ test-chal..│ 3    │
│ ├─ COCO minival     │ split        │ minival    │ 5    │
│ ├─ COCO val2017     │ split        │ val2017    │ 6    │
│ ├─ COCO 2017 val    │ split        │ val        │ 7    │
│ ├─ COCO 2014 val    │ split        │ val        │ 8    │
│ ├─ COCO-Stuff       │ variant      │ NULL       │ 9    │
│ ├─ COCO Captions    │ derived      │ NULL       │ 10   │
│ ├─ COCO-Text        │ variant      │ NULL       │ 11   │
│ ├─ RefCOCO          │ derived      │ NULL       │ 12   │
│ └─ COCO-WholeBody   │ variant      │ NULL       │ 13   │
└─────────────────────┴──────────────┴────────────┴──────┘
```

### Evaluations (After Migration)
```
┌────┬───────────────────────┬───────────────┬──────────┐
│ ID │ Model                 │ Dataset       │ Split    │
├────┼───────────────────────┼───────────────┼──────────┤
│ 1  │ DETR-DC5 (ResNet-101) │ COCO minival  │ minival  │
│ 2  │ Co-DETR (Swin-L)      │ COCO test-dev │ test-dev │
│ 3  │ Co-DETR               │ COCO test-dev │ test-dev │
└────┴───────────────────────┴───────────────┴──────────┘
```

## How It Works

### For Benchmarks/Leaderboards

1. **Query Datasets for a Task** (e.g., Object Detection):
   ```python
   GET /api/v1/datasets/?task=object-detection
   ```
   Returns:
   ```json
   [
     {"id": "2", "name": "COCO test-dev", "split_name": "test-dev", ...},
     {"id": "5", "name": "COCO minival", "split_name": "minival", ...},
     {"id": "7", "name": "COCO 2017 val", "split_name": "val", ...},
     ...
   ]
   ```

2. **Query Evaluations for Each Split**:
   ```python
   GET /api/v1/evaluations/?dataset_id=2&task_id=2  # COCO test-dev
   GET /api/v1/evaluations/?dataset_id=5&task_id=2  # COCO minival
   ```
   Each split returns its own independent leaderboard!

3. **Frontend Displays Separate Rows**:
   Just like the legacy screenshot, each split appears as a separate leaderboard entry with its own best model and results.

### For Importing New Evaluations

When importing from legacy PapersWithCode data:

```python
from backend.utils.dataset_utils import find_dataset_by_name

# Legacy data says: "COCO minival"
dataset = find_dataset_by_name(db, "COCO minival")
# Returns: COCO minival dataset (ID: 5, split_name='minival')

# Create evaluation linked to the specific split
evaluation = Evaluation(
    paper_id=paper_id,
    task_id=task_id,
    dataset_id=dataset.id,  # Links to split, not parent!
    ...
)
```

## Example Queries

### Get all COCO splits for benchmarks
```sql
SELECT id, name, split_name
FROM datasets
WHERE parent_dataset_id = 1 AND variant_type = 'split'
ORDER BY name;
```

### Get leaderboard for COCO test-dev
```sql
SELECT
    e.model_name,
    e.metrics,
    p.title as paper_title,
    d.name as dataset_name,
    d.split_name
FROM evaluations e
JOIN papers p ON e.paper_id = p.id
JOIN datasets d ON e.dataset_id = d.id
WHERE d.split_name = 'test-dev'
    AND d.parent_dataset_id = 1
ORDER BY (e.metrics->>'AP')::float DESC;
```

### Get all evaluations grouped by split
```sql
SELECT
    d.name as dataset_name,
    d.split_name,
    COUNT(e.id) as eval_count
FROM datasets d
LEFT JOIN evaluations e ON d.id = e.dataset_id
WHERE d.parent_dataset_id = 1
GROUP BY d.id, d.name, d.split_name
ORDER BY d.name;
```

## Files Created/Modified

### New Files
- `backend/utils/dataset_utils.py` - Dataset matching utilities
- `backend/database/evaluations_setup/migrate_evaluations_to_splits.py` - Migration script
- `backend/database/datasets_setup/populate_coco_variants.py` - COCO population script
- `backend/database/migrations/add_missing_dataset_variant_fields.sql` - Schema migration
- `DATASET_SPLITS_FOR_LEADERBOARDS.md` - This document

### Modified Files
- `backend/models/database.py` - Added variant fields to Dataset model
- `backend/models/api.py` - Added variant fields to Dataset API model
- `backend/services/dataset_service.py` - Return split info in responses

## Usage Examples

### Import Evaluations with Correct Split Detection
```python
from backend.utils.dataset_utils import find_dataset_by_name

# When importing from legacy data
legacy_dataset_name = "COCO test-dev"  # From evaluation-tables.json
dataset = find_dataset_by_name(db, legacy_dataset_name)
# Automatically finds: COCO test-dev (ID: 2, split_name='test-dev')

evaluation = Evaluation(
    dataset_id=dataset.id,  # Correctly linked to split
    ...
)
```

### Create New Split On-The-Fly
```python
from backend.utils.dataset_utils import get_or_create_dataset_split

coco = db.query(Dataset).filter(Dataset.name == "COCO").first()

# Create "COCO val2018" if it doesn't exist
val2018 = get_or_create_dataset_split(
    db=db,
    parent_dataset=coco,
    split_name="val2018",
    description="COCO 2018 validation split"
)
```

### Query Splits for Frontend
```python
# Get all COCO splits for benchmark dropdown
splits = db.query(Dataset).filter(
    Dataset.parent_dataset_id == coco_id,
    Dataset.variant_type == 'split'
).order_by(Dataset.name).all()

# Returns: [COCO 2014 val, COCO 2017 val, COCO minival, COCO test-dev, ...]
```

## Migration Script Usage

### Check what would be migrated (dry run)
```bash
uv run --env-file backend/keys.env backend/database/evaluations_setup/migrate_evaluations_to_splits.py
```

### Apply the migration
```bash
uv run --env-file backend/keys.env backend/database/evaluations_setup/migrate_evaluations_to_splits.py --apply
```

## Benefits

1. **✅ Accurate Benchmarking**: Each split has its own leaderboard with correct results
2. **✅ Legacy Compatibility**: Matches original PapersWithCode behavior exactly
3. **✅ Automatic Detection**: Smart matching finds correct splits from legacy data
4. **✅ Scalable**: Works for any dataset (ImageNet, PASCAL VOC, etc.)
5. **✅ Flexible**: Can create splits on-the-fly as needed
6. **✅ Clean API**: Splits appear as separate datasets in all endpoints

## Next Steps

### For Other Datasets
Apply the same pattern to other major datasets:

```bash
# ImageNet splits (val, test, val-in-distribution, val-out-of-distribution)
# PASCAL VOC splits (2007 test, 2012 test, 2007+2012)
# CIFAR splits (CIFAR-10, CIFAR-100)
```

### For Bulk Import
Use the helper function when importing evaluations:

```python
from backend.utils.dataset_utils import find_dataset_by_name

# In your import loop
for eval_row in legacy_evaluations:
    dataset_name = eval_row['dataset']  # e.g., "COCO test-dev"
    dataset = find_dataset_by_name(db, dataset_name)

    if dataset:
        # Create evaluation linked to correct split
        ...
```

## Verification

Run these queries to verify everything is working:

```bash
# Check dataset hierarchy
sudo -u postgres psql -d paperswithcode_hf -c "SELECT name, variant_type, split_name, parent_dataset_id FROM datasets WHERE name LIKE '%COCO%' ORDER BY id;"

# Check evaluations are on correct splits
sudo -u postgres psql -d paperswithcode_hf -c "SELECT e.id, e.model_name, d.name, d.split_name FROM evaluations e JOIN datasets d ON e.dataset_id = d.id;"

# Check hierarchy view
sudo -u postgres psql -d paperswithcode_hf -c "SELECT name, variant_type, level, path FROM dataset_hierarchies WHERE path LIKE '%COCO%' ORDER BY path;"
```

## Conclusion

The system now properly handles dataset splits for separate leaderboards, exactly as shown in the legacy PapersWithCode screenshot. Each split (COCO test-dev, COCO minival, etc.) has its own independent leaderboard with different best models and results. The implementation is automatic, scalable, and ready to handle evaluations from any source! 🎉
