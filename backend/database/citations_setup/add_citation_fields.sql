-- Migration script to add citation fields to existing papers table
-- Run this script if you already have a papers table without citation fields

-- Add citation-related columns
ALTER TABLE papers
ADD COLUMN IF NOT EXISTS citation_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS citation_updated_at TIMESTAMP WITH TIME ZONE;

-- Add indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_papers_citation_count ON papers(citation_count DESC);
CREATE INDEX IF NOT EXISTS idx_papers_semantic_scholar_id ON papers(semantic_scholar_id);

-- Add comments for documentation
COMMENT ON COLUMN papers.citation_count IS 'Number of citations from Semantic Scholar API';
COMMENT ON COLUMN papers.semantic_scholar_id IS 'Semantic Scholar paper ID for API lookups';
COMMENT ON COLUMN papers.citation_updated_at IS 'Timestamp when citation count was last updated';

-- Update any existing papers to have citation_count = 0 if NULL
UPDATE papers SET citation_count = 0 WHERE citation_count IS NULL;
