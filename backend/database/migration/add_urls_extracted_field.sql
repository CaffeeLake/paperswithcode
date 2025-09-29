-- Migration: Add urls_extracted field to papers table
-- This field tracks whether AI URL extraction has been attempted for a paper
-- Simplifies the complex query logic in batch_extract.py

-- Add the new boolean field with default value FALSE
ALTER TABLE papers
ADD COLUMN urls_extracted BOOLEAN DEFAULT FALSE;

-- Add index for efficient querying of unprocessed papers
CREATE INDEX idx_papers_urls_extracted ON papers(urls_extracted);

-- Add comment for documentation
COMMENT ON COLUMN papers.urls_extracted IS 'Flag indicating if AI URL extraction has been attempted for this paper';

-- Optional: Update existing papers that already have URLs to mark them as processed
-- This prevents re-processing papers that already have GitHub repos or project pages
UPDATE papers
SET urls_extracted = TRUE
WHERE id IN (
    -- Papers that have GitHub repositories
    SELECT DISTINCT p.id
    FROM papers p
    JOIN paper_repositories pr ON p.id = pr.paper_id
    UNION
    -- Papers that have project pages
    SELECT DISTINCT p.id
    FROM papers p
    JOIN paper_project_pages ppp ON p.id = ppp.paper_id
    UNION
    -- Papers that were marked as processed with no results (AI_PROCESSED_NO_RESULTS marker)
    SELECT DISTINCT p.id
    FROM papers p
    JOIN paper_repositories pr ON p.id = pr.paper_id
    JOIN repositories r ON pr.repository_id = r.id
    WHERE r.url = 'AI_PROCESSED_NO_RESULTS' AND r.source = 'ai_extraction'
);

-- Show statistics after migration
SELECT
    COUNT(*) as total_papers,
    COUNT(*) FILTER (WHERE urls_extracted = TRUE) as papers_already_processed,
    COUNT(*) FILTER (WHERE urls_extracted = FALSE) as papers_need_processing,
    ROUND(
        COUNT(*) FILTER (WHERE urls_extracted = TRUE) * 100.0 / COUNT(*),
        2
    ) as percent_already_processed
FROM papers;
