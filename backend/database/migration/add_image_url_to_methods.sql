-- Migration: Add image_url column to methods table
-- Date: October 5, 2025
-- Description: Add support for method images/diagrams

-- Add image_url column to methods table
ALTER TABLE methods ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000);

-- Add comment to document the column
COMMENT ON COLUMN methods.image_url IS 'URL to an image/diagram representing the method (e.g., architecture diagram, workflow)';

-- Create index for querying methods with images
CREATE INDEX IF NOT EXISTS idx_methods_has_image ON methods(image_url) WHERE image_url IS NOT NULL;

-- Verify the migration
SELECT 'Migration complete: image_url column added to methods table' AS status;
