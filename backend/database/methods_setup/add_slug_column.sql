-- Add slug column to methods table
ALTER TABLE methods ADD COLUMN IF NOT EXISTS slug VARCHAR(255);

-- Grant permissions to application user
GRANT ALL PRIVILEGES ON TABLE methods TO paperswithcode_user;
