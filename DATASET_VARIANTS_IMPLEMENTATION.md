# Dataset Variants & Splits Implementation

## Summary

Successfully implemented a structured approach (Option B) for handling dataset variants and splits in the PapersWithCode database. This allows the system to properly represent relationships between datasets like COCO and its many variants (COCO test-dev, COCO-Stuff, COCO Captions, etc.).

## What Was Implemented

### 1. Database Schema Changes

Added new columns to the `datasets` table:

- **`variant_type`**: Categorizes the type of dataset relationship
  - `split`: Different evaluation splits (test-dev, minival, val2017)
  - `variant`: Modified annotations (COCO-Stuff, COCO-Text)
  - `subset`: Filtered subsets (COCO-Animals, COCO-Persons)
  - `derived`: Different purpose/task (COCO Captions, RefCOCO)
  - `augmented`: Augmented versions (COCO+)

- **`split_name`**: Short name for splits (e.g., "test-dev", "minival")
- **`introduced_year`**: Year the dataset/variant was introduced
- **`paper_url`**: URL to the paper that introduced the dataset
- **`parent_dataset_id`**: Links to parent dataset (already existed)

### 2. Database Views

Created three helpful views for querying dataset hierarchies:

- **`base_datasets`**: Shows only root datasets (no parent)
- **`datasets_with_parent`**: Joins datasets with parent information
- **`dataset_hierarchies`**: Recursive view showing full hierarchy paths

### 3. Updated Models

**SQLAlchemy Models** (`backend/models/database.py`):
- Added `variant_type`, `split_name`, `introduced_year`, `paper_url` fields

**Pydantic API Models** (`backend/models/api.py`):
- Added same fields to Dataset API response model

### 4. Scripts & Tools

**Migration Script**:
- `backend/database/migrations/add_missing_dataset_variant_fields.sql`
- Adds new columns, indexes, constraints, and views

**Population Script**:
- `backend/database/datasets_setup/populate_coco_variants.py`
- Populates COCO and its 11 variants/splits with full metadata

**Documentation**:
- `backend/database/datasets_setup/README.md`
- Comprehensive guide on using the dataset variants system

## Current Database State

Successfully populated COCO dataset with:

### Base Dataset
- **COCO** (Common Objects in Context)

### 6 Splits
1. COCO test-dev
2. COCO test-challenge
3. COCO minival
4. COCO val2017
5. COCO 2017 val
6. COCO 2014 val

### 5 Major Variants
1. COCO-Stuff (variant)
2. COCO Captions (derived)
3. COCO-Text (variant)
4. RefCOCO (derived)
5. COCO-WholeBody (variant)

## Example Queries

### Get all COCO variants
```sql
SELECT name, variant_type, split_name
FROM datasets
WHERE parent_dataset_id = (SELECT id FROM datasets WHERE name = 'COCO')
ORDER BY variant_type, name;
```

### View dataset hierarchy
```sql
SELECT name, variant_type, split_name, level, path
FROM dataset_hierarchies
WHERE path LIKE '%COCO%'
ORDER BY path;
```

### Get only splits
```sql
SELECT name, split_name
FROM datasets
WHERE parent_dataset_id = 1 AND variant_type = 'split';
```

## Benefits

1. **Structured Data**: Clear parent-child relationships between datasets
2. **Explicit Typing**: variant_type field makes the relationship type clear
3. **Easy Querying**: SQL views make it simple to query hierarchies
4. **Scalable**: Can be applied to other datasets (ImageNet, PASCAL VOC, etc.)
5. **Backward Compatible**: Existing datasets without variants still work

## Legacy PapersWithCode Comparison

### How Legacy PWC Handled It
- Base datasets had full entries
- Major variants were separate independent entries
- Test splits were just referenced as strings in benchmarks
- No formal parent-child relationships

### Our Improved Approach
- ✅ Structured parent-child relationships
- ✅ Explicit variant type categorization
- ✅ Formal split tracking with split_name field
- ✅ Recursive SQL views for hierarchy queries
- ✅ Complete metadata for every variant

## API Usage

The dataset variants are now fully integrated into the API:

```python
# GET /api/v1/datasets/1
{
  "id": "1",
  "name": "COCO",
  "variant_type": null,
  "split_name": null,
  "parent_dataset_id": null,
  ...
}

# GET /api/v1/datasets/2
{
  "id": "2",
  "name": "COCO test-dev",
  "variant_type": "split",
  "split_name": "test-dev",
  "parent_dataset_id": "1",
  ...
}
```

## Future Enhancements

1. **Frontend Visualization**: Show dataset trees in the UI
2. **Automatic Detection**: Import splits from evaluation tables automatically
3. **More Datasets**: Apply to ImageNet, PASCAL VOC, etc.
4. **Variant Comparison**: Tools to compare results across variants
5. **Search Filtering**: Filter benchmarks by specific splits

## Files Changed

### Database
- `backend/database/migrations/add_missing_dataset_variant_fields.sql` (new)
- `backend/database/migrations/rollback_dataset_variants_and_splits.sql` (new)
- `backend/database/migrations/run_add_dataset_variants_and_splits.py` (new)

### Scripts
- `backend/database/datasets_setup/populate_coco_variants.py` (new)
- `backend/database/datasets_setup/README.md` (new)

### Models
- `backend/models/database.py` (updated Dataset model)
- `backend/models/api.py` (updated Dataset API model)

### Documentation
- `DATASET_VARIANTS_IMPLEMENTATION.md` (this file)

## Running the Implementation

```bash
# 1. Apply the migration
sudo -u postgres psql -d paperswithcode_hf -f backend/database/migrations/add_missing_dataset_variant_fields.sql

# 2. Populate COCO variants
uv run --env-file backend/keys.env backend/database/datasets_setup/populate_coco_variants.py

# 3. Verify
sudo -u postgres psql -d paperswithcode_hf -c "SELECT name, variant_type FROM datasets WHERE parent_dataset_id = 1 OR id = 1;"
```

## Conclusion

The dataset variants and splits system is now fully implemented and working. COCO and its 11 variants have been successfully populated with proper metadata, and the system is ready to be extended to other datasets as needed.
