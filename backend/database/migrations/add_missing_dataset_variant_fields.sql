-- Migration: Add missing fields for dataset variants and splits
-- This is a simplified version that only adds fields that don't already exist
--
-- Usage: sudo -u postgres psql -d paperswithcode_hf -f add_missing_dataset_variant_fields.sql

-- Add only the missing columns (parent_dataset_id already exists)
ALTER TABLE datasets
    ADD COLUMN IF NOT EXISTS variant_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS split_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS introduced_year INTEGER,
    ADD COLUMN IF NOT EXISTS paper_url VARCHAR(500);

-- Create indexes on new columns
CREATE INDEX IF NOT EXISTS idx_datasets_variant_type ON datasets(variant_type);
CREATE INDEX IF NOT EXISTS idx_datasets_split_name ON datasets(split_name);
CREATE INDEX IF NOT EXISTS idx_datasets_introduced_year ON datasets(introduced_year);

-- Add check constraint for variant_type values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_variant_type'
    ) THEN
        ALTER TABLE datasets
            ADD CONSTRAINT check_variant_type
            CHECK (variant_type IS NULL OR variant_type IN (
                'split',       -- Different split of same dataset (test-dev, minival, train, val)
                'variant',     -- Different variant with modified annotations (COCO-Stuff, COCO-Text)
                'subset',      -- Subset of the original dataset (COCO-Animals, COCO-Persons)
                'derived',     -- Derived dataset with different purpose (COCO Captions, RefCOCO)
                'augmented'    -- Augmented version with additional data
            ));
    END IF;
END $$;

-- Add comments for documentation
COMMENT ON COLUMN datasets.parent_dataset_id IS 'Reference to parent dataset (NULL for base datasets)';
COMMENT ON COLUMN datasets.variant_type IS 'Type of dataset variant: split, variant, subset, derived, or augmented';
COMMENT ON COLUMN datasets.split_name IS 'Name of the split (e.g., test-dev, minival, val2017)';
COMMENT ON COLUMN datasets.introduced_year IS 'Year the dataset or variant was introduced';
COMMENT ON COLUMN datasets.paper_url IS 'URL to paper that introduced this dataset';

-- Create views if they don't exist

-- Base datasets view
CREATE OR REPLACE VIEW base_datasets AS
SELECT * FROM datasets WHERE parent_dataset_id IS NULL;

-- Datasets with parent information
CREATE OR REPLACE VIEW datasets_with_parent AS
SELECT
    d.id,
    d.name,
    d.full_name,
    d.description,
    d.variant_type,
    d.split_name,
    d.url,
    d.hf_url,
    d.homepage,
    d.introduced_year,
    d.license_name,
    d.parent_dataset_id,
    p.name as parent_name,
    p.full_name as parent_full_name,
    d.created_at,
    d.updated_at
FROM datasets d
LEFT JOIN datasets p ON d.parent_dataset_id = p.id;

-- Recursive hierarchy view
CREATE OR REPLACE VIEW dataset_hierarchies AS
WITH RECURSIVE dataset_tree AS (
    -- Base case: top-level datasets
    SELECT
        id,
        name,
        full_name,
        parent_dataset_id,
        variant_type,
        split_name,
        0 as level,
        CAST(name AS TEXT) as path
    FROM datasets
    WHERE parent_dataset_id IS NULL

    UNION ALL

    -- Recursive case: child datasets
    SELECT
        d.id,
        d.name,
        d.full_name,
        d.parent_dataset_id,
        d.variant_type,
        d.split_name,
        dt.level + 1,
        CAST(dt.path || ' > ' || d.name AS TEXT)
    FROM datasets d
    INNER JOIN dataset_tree dt ON d.parent_dataset_id = dt.id
)
SELECT
    id,
    name,
    full_name,
    parent_dataset_id,
    variant_type,
    split_name,
    level,
    path
FROM dataset_tree
ORDER BY path;

-- Add view comments
COMMENT ON VIEW base_datasets IS 'Datasets without a parent (base/root datasets)';
COMMENT ON VIEW datasets_with_parent IS 'Datasets with parent information joined';
COMMENT ON VIEW dataset_hierarchies IS 'Recursive view showing full dataset hierarchy paths';

-- Analyze table for query optimization
ANALYZE datasets;
