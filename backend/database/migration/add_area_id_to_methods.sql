-- Migration: Add area_id column to methods table
-- Date: October 4, 2025
-- Description: Connect methods to areas (one-to-many relationship)

-- Add area_id column to methods table
ALTER TABLE methods ADD COLUMN IF NOT EXISTS area_id BIGINT;

-- Add foreign key constraint
ALTER TABLE methods
ADD CONSTRAINT fk_methods_area_id
FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL;

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_methods_area_id ON methods(area_id);

-- Verify the migration
SELECT 'Migration complete: area_id column added to methods table' AS status;
