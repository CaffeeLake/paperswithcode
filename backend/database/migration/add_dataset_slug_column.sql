-- Migration: Add slug column to datasets table
-- Date: 2025-10-14
-- Description: Adds a slug column to datasets table for URL-friendly identifiers

-- Add slug column to datasets table
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS slug VARCHAR(255) UNIQUE;

-- Create index on slug for faster lookups
CREATE INDEX IF NOT EXISTS idx_datasets_slug ON datasets(slug);

-- Generate slugs for existing datasets based on their names
-- This creates URL-friendly slugs by:
-- 1. Converting to lowercase
-- 2. Replacing spaces and special characters with hyphens
-- 3. Removing multiple consecutive hyphens
-- 4. Trimming leading/trailing hyphens
UPDATE datasets
SET slug = LOWER(
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(name, '[^a-zA-Z0-9\s-]', '', 'g'),
            '\s+', '-', 'g'
        ),
        '-+', '-', 'g'
    )
)
WHERE slug IS NULL;

-- Handle duplicate slugs by appending the dataset ID
UPDATE datasets d1
SET slug = d1.slug || '-' || d1.id
WHERE EXISTS (
    SELECT 1
    FROM datasets d2
    WHERE d2.slug = d1.slug
    AND d2.id < d1.id
);

-- For any remaining NULL slugs (edge cases), use "dataset-{id}" format
UPDATE datasets
SET slug = 'dataset-' || id
WHERE slug IS NULL OR slug = '';

-- Verify the migration
SELECT COUNT(*) as total_datasets,
       COUNT(slug) as datasets_with_slug,
       COUNT(DISTINCT slug) as unique_slugs
FROM datasets;
