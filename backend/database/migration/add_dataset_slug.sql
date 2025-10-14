-- Migration: Add slug column to datasets table
-- Purpose: Enable URL-friendly dataset identifiers for benchmark pages
-- Date: 2025-10-14

-- Add slug column (nullable initially)
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS slug VARCHAR(255);

-- Generate slugs from existing dataset names
-- Convert to lowercase and replace non-alphanumeric characters with hyphens
UPDATE datasets
SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'))
WHERE slug IS NULL;

-- Remove leading/trailing hyphens
UPDATE datasets
SET slug = regexp_replace(regexp_replace(slug, '^-+', ''), '-+$', '')
WHERE slug IS NOT NULL;

-- Make slug NOT NULL after populating
ALTER TABLE datasets ALTER COLUMN slug SET NOT NULL;

-- Add unique constraint
ALTER TABLE datasets ADD CONSTRAINT datasets_slug_unique UNIQUE (slug);

-- Add index for fast lookups
CREATE INDEX IF NOT EXISTS idx_datasets_slug ON datasets(slug);

-- Display summary
SELECT 'Dataset slug migration completed' AS status;
SELECT COUNT(*) AS total_datasets, COUNT(DISTINCT slug) AS unique_slugs FROM datasets;
