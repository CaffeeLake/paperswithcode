-- Migration: Add support for dataset variants and splits
-- This allows datasets to have parent/child relationships (e.g., COCO -> COCO test-dev)
-- and different variants (e.g., COCO -> COCO-Stuff, COCO Captions)
--
-- Usage: psql -d paperswithcode_hf -f add_dataset_variants_and_splits.sql

-- Add new columns to datasets table
ALTER TABLE datasets
    ADD COLUMN parent_dataset_id BIGINT REFERENCES datasets(id) ON DELETE SET NULL,
    ADD COLUMN variant_type VARCHAR(100),  -- e.g., 'split', 'variant', 'subset', 'derived'
    ADD COLUMN split_name VARCHAR(100),     -- e.g., 'test-dev', 'minival', 'val2017', 'train'
    ADD COLUMN introduced_year INTEGER,     -- Year this dataset/variant was introduced
    ADD COLUMN paper_title VARCHAR(1000),   -- Paper that introduced this dataset
    ADD COLUMN paper_url VARCHAR(500),      -- URL to the paper
    ADD COLUMN homepage VARCHAR(500),       -- Official dataset homepage
    ADD COLUMN license_name VARCHAR(255),   -- License (e.g., "CC BY 4.0", "MIT")
    ADD COLUMN license_url VARCHAR(500);    -- URL to license terms

-- Create index on parent_dataset_id for efficient hierarchical queries
CREATE INDEX idx_datasets_parent_id ON datasets(parent_dataset_id);
CREATE INDEX idx_datasets_variant_type ON datasets(variant_type);
CREATE INDEX idx_datasets_split_name ON datasets(split_name);
CREATE INDEX idx_datasets_introduced_year ON datasets(introduced_year);

-- Add check constraint for variant_type values
ALTER TABLE datasets
    ADD CONSTRAINT check_variant_type
    CHECK (variant_type IS NULL OR variant_type IN (
        'split',       -- Different split of same dataset (test-dev, minival, train, val)
        'variant',     -- Different variant with modified annotations (COCO-Stuff, COCO-Text)
        'subset',      -- Subset of the original dataset (COCO-Animals, COCO-Persons)
        'derived',     -- Derived dataset with different purpose (COCO Captions, RefCOCO)
        'augmented'    -- Augmented version with additional data
    ));

-- Add comments for documentation
COMMENT ON COLUMN datasets.parent_dataset_id IS 'Reference to parent dataset (NULL for base datasets)';
COMMENT ON COLUMN datasets.variant_type IS 'Type of dataset variant: split, variant, subset, derived, or augmented';
COMMENT ON COLUMN datasets.split_name IS 'Name of the split (e.g., test-dev, minival, val2017)';
COMMENT ON COLUMN datasets.introduced_year IS 'Year the dataset or variant was introduced';
COMMENT ON COLUMN datasets.paper_title IS 'Title of the paper that introduced this dataset';
COMMENT ON COLUMN datasets.paper_url IS 'URL to the paper that introduced this dataset';
COMMENT ON COLUMN datasets.homepage IS 'Official homepage URL for the dataset';
COMMENT ON COLUMN datasets.license_name IS 'License name (e.g., CC BY 4.0, MIT, Custom)';
COMMENT ON COLUMN datasets.license_url IS 'URL to the full license terms';

-- Create a view for base datasets (no parent)
CREATE VIEW base_datasets AS
SELECT * FROM datasets WHERE parent_dataset_id IS NULL;

-- Create a view for datasets with their parent information
CREATE VIEW datasets_with_parent AS
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

-- Create a recursive view to show full dataset hierarchies
CREATE VIEW dataset_hierarchies AS
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
        name as path
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
        dt.path || ' > ' || d.name
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

-- Example data: Update COCO to be the base dataset and add variants
-- This is commented out - run separately if needed:

/*
-- First, ensure we have the base COCO dataset
UPDATE datasets
SET
    full_name = 'Common Objects in Context',
    introduced_year = 2014,
    paper_title = 'Microsoft COCO: Common Objects in Context',
    paper_url = 'https://arxiv.org/abs/1405.0312',
    homepage = 'https://cocodataset.org',
    license_name = 'CC BY 4.0',
    license_url = 'https://cocodataset.org/#termsofuse'
WHERE name = 'COCO' OR name = 'MS COCO';

-- Now add COCO splits (assuming COCO id is 1)
INSERT INTO datasets (name, full_name, parent_dataset_id, variant_type, split_name, description, url)
VALUES
    ('COCO test-dev', 'COCO test-dev Split', 1, 'split', 'test-dev', 'COCO test-dev evaluation split', 'https://cocodataset.org'),
    ('COCO minival', 'COCO minival Split', 1, 'split', 'minival', 'COCO minival evaluation split (5k images)', 'https://cocodataset.org'),
    ('COCO val2017', 'COCO val2017 Split', 1, 'split', 'val2017', 'COCO 2017 validation split', 'https://cocodataset.org'),
    ('COCO test-challenge', 'COCO test-challenge Split', 1, 'split', 'test-challenge', 'COCO test-challenge evaluation split', 'https://cocodataset.org')
ON CONFLICT DO NOTHING;
*/

-- Analyze table for query optimization
ANALYZE datasets;
