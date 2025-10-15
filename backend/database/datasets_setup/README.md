# Dataset Setup & Management

This directory contains scripts for setting up and managing datasets in the database, with special support for dataset variants and splits.

## Dataset Hierarchy & Variants

The database now supports hierarchical relationships between datasets, allowing you to model:

### Variant Types

1. **`split`** - Different evaluation splits of the same dataset
   - Examples: COCO test-dev, COCO minival, COCO val2017
   - Same data source, different subsets for different purposes

2. **`variant`** - Different annotations or modifications of the base dataset
   - Examples: COCO-Stuff (adds stuff annotations), COCO-Text (adds text annotations)
   - Same images, different annotation types

3. **`subset`** - Filtered subset of the original dataset
   - Examples: COCO-Animals, COCO-Persons
   - Subset of images focusing on specific categories

4. **`derived`** - New dataset derived from the original with different purpose
   - Examples: COCO Captions, RefCOCO
   - Different task/purpose using COCO images

5. **`augmented`** - Original dataset with additional data
   - Examples: COCO+, COCO-MIX
   - Augmented or expanded versions

## Database Schema

### Key Fields

- **`parent_dataset_id`**: References the parent dataset (NULL for base datasets)
- **`variant_type`**: One of: split, variant, subset, derived, augmented
- **`split_name`**: Name of the split (e.g., "test-dev", "minival", "val2017")
- **`introduced_year`**: Year the dataset or variant was introduced
- **`paper_title`**: Title of paper that introduced this dataset
- **`paper_url`**: URL to the introducing paper
- **`homepage`**: Official dataset homepage
- **`license_name`**: License (e.g., "CC BY 4.0", "MIT")
- **`license_url`**: URL to license terms

### Database Views

The migration creates several helpful views:

1. **`base_datasets`** - Only base datasets (no parent)
2. **`datasets_with_parent`** - Datasets with parent information joined
3. **`dataset_hierarchies`** - Recursive view showing full hierarchy paths

## Scripts

### 1. Migration Scripts

**Apply the migration:**
```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_dataset_variants_and_splits.sql
```

**Rollback the migration:**
```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/rollback_dataset_variants_and_splits.sql
```

### 2. COCO Dataset Setup

**Populate COCO and its variants:**
```bash
uv run --env-file backend/keys.env backend/database/datasets_setup/populate_coco_variants.py
```

This script:
- Creates/updates the base COCO dataset with full metadata
- Creates common COCO splits (test-dev, minival, val2017, etc.)
- Creates major COCO variants (COCO-Stuff, COCO Captions, COCO-Text, etc.)

### 3. Import Legacy Data

**Import COCO dataset from legacy data:**
```bash
uv run --env-file backend/keys.env backend/database/datasets_setup/import_coco_dataset.py
```

## Example Queries

### Get all COCO variants and splits
```sql
SELECT
    id,
    name,
    variant_type,
    split_name,
    introduced_year
FROM datasets
WHERE parent_dataset_id = (SELECT id FROM datasets WHERE name = 'COCO')
ORDER BY variant_type, name;
```

### Get dataset hierarchy
```sql
SELECT
    level,
    path,
    name,
    variant_type,
    split_name
FROM dataset_hierarchies
WHERE path LIKE '%COCO%'
ORDER BY path;
```

### Get all base datasets (no parent)
```sql
SELECT id, name, full_name, introduced_year
FROM base_datasets
ORDER BY name;
```

### Find datasets with their parent
```sql
SELECT
    d.name as dataset_name,
    d.variant_type,
    d.split_name,
    p.name as parent_name
FROM datasets_with_parent d
WHERE parent_name IS NOT NULL
ORDER BY parent_name, variant_type, dataset_name;
```

## API Usage

### Get dataset with variant information
```python
from backend.services.dataset_service import get_dataset_by_id

dataset = get_dataset_by_id(dataset_id=1)
print(f"Dataset: {dataset.name}")
print(f"Variant type: {dataset.variant_type}")
print(f"Split: {dataset.split_name}")
print(f"Parent: {dataset.parent_dataset_id}")
```

### Get all variants of a dataset
```python
from sqlalchemy import select
from backend.models.database import Dataset

# Get all COCO variants
coco = session.query(Dataset).filter(Dataset.name == "COCO").first()
variants = session.query(Dataset).filter(
    Dataset.parent_dataset_id == coco.id
).all()

for variant in variants:
    print(f"{variant.name} ({variant.variant_type})")
```

## Legacy PapersWithCode Data Insights

Based on analysis of `data/legacy_pwc_data/evaluation-tables.json` and `data/legacy_pwc_data/jul-28-datasets.json`:

### How Legacy PWC Handled Datasets

1. **Base datasets** like "COCO" were full dataset entries with complete metadata
2. **Major variants** (COCO-Stuff, COCO Captions) were separate full dataset entries
3. **Test splits** (test-dev, minival) were referenced as strings in benchmarks but NOT as formal dataset entries
4. **No parent_dataset field** was used - all variants were independent

### Our Improved Approach

1. **Structured hierarchy** with parent-child relationships
2. **Explicit variant types** (split, variant, subset, derived, augmented)
3. **Split names** for easy filtering and identification
4. **Comprehensive metadata** for each variant
5. **SQL views** for easy querying of hierarchies

### Dataset Split Patterns Found

Common COCO splits in evaluation tables:
- `COCO test-dev` - Most common benchmark split
- `COCO test-challenge` - Official challenge submissions
- `COCO minival` - 5K validation subset
- `COCO val2017` - 2017 validation split
- `COCO 2017 val` - Alternative name for val2017
- `COCO 2014 val` - 2014 validation split

### Major COCO Variants Found

From the datasets file:
- COCO-Stuff (stuff segmentation)
- COCO Captions (image captioning)
- COCO-Text (text detection)
- RefCOCO (referring expressions)
- COCO-WholeBody (whole-body pose)
- COCO-QA (visual QA)
- DensePose-COCO (dense pose estimation)

## Future Enhancements

1. **Automatic variant detection** from evaluation imports
2. **Variant relationship visualization** in frontend
3. **Unified benchmarking** across splits
4. **Variant comparison tools** for researchers
5. **Import scripts** for other major datasets (ImageNet, PASCAL VOC, etc.)

## Troubleshooting

### Migration fails with "column already exists"
The parent_dataset_id field might already exist. Check with:
```sql
\d datasets
```

### Can't find COCO dataset
Make sure you've run the import script:
```bash
uv run --env-file backend/keys.env backend/database/datasets_setup/populate_coco_variants.py
```

### Foreign key constraint errors
Ensure you're setting parent_dataset_id to an existing dataset ID:
```sql
SELECT id, name FROM datasets WHERE name = 'COCO';
```
