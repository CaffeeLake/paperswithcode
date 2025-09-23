-- Add arXiv category fields to papers table
-- This enables filtering by subject area (e.g., computer science only)

-- Add category columns to papers table
ALTER TABLE papers
ADD COLUMN IF NOT EXISTS primary_category VARCHAR(50),
ADD COLUMN IF NOT EXISTS all_categories TEXT[];

-- Create indexes for efficient filtering
CREATE INDEX IF NOT EXISTS idx_papers_primary_category ON papers(primary_category);
CREATE INDEX IF NOT EXISTS idx_papers_cs_only ON papers(primary_category) WHERE primary_category LIKE 'cs.%';

-- Add comments for documentation
COMMENT ON COLUMN papers.primary_category IS 'Primary arXiv category (e.g., cs.AI, eess.IV)';
COMMENT ON COLUMN papers.all_categories IS 'Array of all arXiv categories for this paper';

-- Create view for computer science papers only
CREATE OR REPLACE VIEW cs_papers AS
SELECT * FROM papers
WHERE primary_category LIKE 'cs.%'
  AND is_latest_version = TRUE;

-- Create view for latest CS papers with full details
CREATE OR REPLACE VIEW latest_cs_papers AS
SELECT * FROM papers
WHERE primary_category LIKE 'cs.%'
  AND is_latest_version = TRUE;

COMMENT ON VIEW cs_papers IS 'Computer Science papers only (all versions)';
COMMENT ON VIEW latest_cs_papers IS 'Latest versions of Computer Science papers only';

-- Show current statistics (run after populating categories)
-- SELECT
--     CASE
--         WHEN primary_category LIKE 'cs.%' THEN 'Computer Science'
--         WHEN primary_category LIKE 'eess.%' THEN 'Electrical Engineering'
--         WHEN primary_category LIKE 'stat.%' THEN 'Statistics'
--         WHEN primary_category LIKE 'q-bio.%' THEN 'Biology'
--         WHEN primary_category LIKE 'q-fin.%' THEN 'Finance'
--         WHEN primary_category LIKE 'econ.%' THEN 'Economics'
--         ELSE 'Other'
--     END as category_group,
--     COUNT(*) as paper_count,
--     ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM papers WHERE primary_category IS NOT NULL), 2) as percentage
-- FROM papers
-- WHERE primary_category IS NOT NULL
-- GROUP BY category_group
-- ORDER BY paper_count DESC;
