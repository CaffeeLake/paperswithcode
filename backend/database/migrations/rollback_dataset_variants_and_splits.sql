-- Rollback: Remove dataset variants and splits support
-- This reverses the add_dataset_variants_and_splits.sql migration
--
-- Usage: psql -d paperswithcode_hf -f rollback_dataset_variants_and_splits.sql

-- Drop views first (they depend on the columns)
DROP VIEW IF EXISTS dataset_hierarchies;
DROP VIEW IF EXISTS datasets_with_parent;
DROP VIEW IF EXISTS base_datasets;

-- Drop indexes
DROP INDEX IF EXISTS idx_datasets_parent_id;
DROP INDEX IF EXISTS idx_datasets_variant_type;
DROP INDEX IF EXISTS idx_datasets_split_name;
DROP INDEX IF EXISTS idx_datasets_introduced_year;

-- Remove columns from datasets table
ALTER TABLE datasets
    DROP COLUMN IF EXISTS parent_dataset_id,
    DROP COLUMN IF EXISTS variant_type,
    DROP COLUMN IF EXISTS split_name,
    DROP COLUMN IF EXISTS introduced_year,
    DROP COLUMN IF EXISTS paper_title,
    DROP COLUMN IF EXISTS paper_url,
    DROP COLUMN IF EXISTS homepage,
    DROP COLUMN IF EXISTS license_name,
    DROP COLUMN IF EXISTS license_url;

-- Analyze table for query optimization
ANALYZE datasets;
