-- Migration: Add image_credit column to methods table
-- Date: October 5, 2025
-- Description: Add support for image credit/attribution

-- Add image_credit column to methods table
ALTER TABLE methods ADD COLUMN IF NOT EXISTS image_credit VARCHAR(1000);

-- Add comment to document the column
COMMENT ON COLUMN methods.image_credit IS 'Attribution/credit for the method image (e.g., paper URL, source URL)';

-- Verify the migration
SELECT 'Migration complete: image_credit column added to methods table' AS status;
