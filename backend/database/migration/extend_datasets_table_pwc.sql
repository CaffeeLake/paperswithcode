-- Extend datasets table with rich PapersWithCode legacy data fields
-- Migration created: October 2025
-- This adds fields from the legacy PWC datasets.json file to enrich our dataset information

-- Add additional metadata fields
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS short_description TEXT;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS homepage VARCHAR(500);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS parent_dataset_id BIGINT REFERENCES datasets(id) ON DELETE SET NULL;

-- Add image/media URLs
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(500);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS verified_image_url VARCHAR(500);

-- Add paper reference (the paper that introduced this dataset)
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS introducing_paper_id BIGINT REFERENCES papers(id) ON DELETE SET NULL;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS introducing_paper_title VARCHAR(500);

-- Add licensing information
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS license_name VARCHAR(255);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS license_url VARCHAR(500);

-- Add introduction date
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS introduced_date DATE;

-- Add modalities as JSONB array (e.g., ["Images", "Videos"])
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS modalities JSONB;

-- Add languages as JSONB array (e.g., ["English", "Chinese"])
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS languages JSONB;

-- Add variants as JSONB array (e.g., ["COCO test-dev", "COCO 2017"])
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS variants JSONB;

-- Add mention/usage count
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS num_papers INTEGER DEFAULT 0;

-- Add warning field (for dataset warnings/notes)
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS warning TEXT;

-- Add PWC source URL (original URL from paperswithcode.com)
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS pwc_url VARCHAR(500);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_datasets_name ON datasets(name);
CREATE INDEX IF NOT EXISTS idx_datasets_parent_dataset_id ON datasets(parent_dataset_id);
CREATE INDEX IF NOT EXISTS idx_datasets_introducing_paper_id ON datasets(introducing_paper_id);
CREATE INDEX IF NOT EXISTS idx_datasets_introduced_date ON datasets(introduced_date);
CREATE INDEX IF NOT EXISTS idx_datasets_num_papers ON datasets(num_papers DESC);

-- Create full-text search indexes
CREATE INDEX IF NOT EXISTS idx_datasets_description_search ON datasets USING gin(to_tsvector('english', COALESCE(description, '')));
CREATE INDEX IF NOT EXISTS idx_datasets_short_description_search ON datasets USING gin(to_tsvector('english', COALESCE(short_description, '')));

-- Add comments for documentation
COMMENT ON COLUMN datasets.short_description IS 'Short description of the dataset (summary)';
COMMENT ON COLUMN datasets.homepage IS 'Official homepage URL of the dataset';
COMMENT ON COLUMN datasets.parent_dataset_id IS 'Parent dataset ID if this is a variant or subset';
COMMENT ON COLUMN datasets.image_url IS 'Main image URL for the dataset';
COMMENT ON COLUMN datasets.thumbnail_url IS 'Thumbnail image URL';
COMMENT ON COLUMN datasets.verified_image_url IS 'Verified image URL from PWC';
COMMENT ON COLUMN datasets.introducing_paper_id IS 'Paper ID that introduced this dataset';
COMMENT ON COLUMN datasets.introducing_paper_title IS 'Title of the paper that introduced this dataset';
COMMENT ON COLUMN datasets.license_name IS 'License name (e.g., MIT, Apache 2.0, Custom)';
COMMENT ON COLUMN datasets.license_url IS 'URL to license details';
COMMENT ON COLUMN datasets.introduced_date IS 'Date when the dataset was introduced';
COMMENT ON COLUMN datasets.modalities IS 'JSONB array of data modalities (e.g., ["Images", "Videos", "Text"])';
COMMENT ON COLUMN datasets.languages IS 'JSONB array of languages (e.g., ["English", "Chinese"])';
COMMENT ON COLUMN datasets.variants IS 'JSONB array of dataset variants/splits (e.g., ["COCO test-dev", "COCO 2017"])';
COMMENT ON COLUMN datasets.num_papers IS 'Number of papers using this dataset';
COMMENT ON COLUMN datasets.warning IS 'Warning or note about the dataset';
COMMENT ON COLUMN datasets.pwc_url IS 'Original PapersWithCode URL (e.g., https://paperswithcode.com/dataset/coco)';
