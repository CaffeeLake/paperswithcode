-- Add metadata columns to tasks table
-- Migration created: October 2025
-- Purpose: Add image_url, image_credit, and useful_leaderboards columns to tasks table

-- Add new columns to tasks table
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000),
ADD COLUMN IF NOT EXISTS image_credit VARCHAR(1000),
ADD COLUMN IF NOT EXISTS useful_leaderboards TEXT;

-- Add comments for documentation
COMMENT ON COLUMN tasks.image_url IS 'URL to task image/visual representation';
COMMENT ON COLUMN tasks.image_credit IS 'Image source/credit information';
COMMENT ON COLUMN tasks.useful_leaderboards IS 'Links to relevant leaderboards for this task';
