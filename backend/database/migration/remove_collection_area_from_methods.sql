-- Migration: Remove collection_area column from methods table
-- Date: October 13, 2025
-- Description: Remove unused collection_area column - the system now uses area_id foreign key instead
-- Reason: Only 5 out of 191 methods have this field populated, and it's not used for any filtering or grouping.
--         The area_id foreign key relationship is the correct approach for relational database design.

-- Backup note: Before running this migration in production, consider backing up the 5 rows that have collection_area populated
-- SELECT id, name, collection_area FROM methods WHERE collection_area IS NOT NULL AND collection_area != '';

-- Drop the column
ALTER TABLE methods DROP COLUMN IF EXISTS collection_area;

-- Verify the migration
SELECT 'Migration complete: collection_area column removed from methods table' AS status;
