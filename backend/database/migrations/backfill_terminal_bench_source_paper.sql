-- Migration: Link Terminal Bench dataset to its introducing paper (arxiv 2601.11868)
-- Description: Backfills datasets.introducing_paper_id, introducing_paper_title,
--              and paper_url for the `terminal-bench` benchmark so the
--              benchmark page exposes its source paper and the paper page
--              shows an "introduced this benchmark" badge.
-- Date: 2026-05-09

WITH source_paper AS (
    SELECT id, arxiv_id, title
    FROM papers
    WHERE arxiv_id = '2601.11868'
        AND is_latest_version = TRUE
    LIMIT 1
)
UPDATE datasets d
SET
    introducing_paper_id = sp.id,
    introducing_paper_title = COALESCE(d.introducing_paper_title, sp.title),
    paper_url = COALESCE(NULLIF(d.paper_url, ''), 'https://arxiv.org/abs/' || sp.arxiv_id)
FROM source_paper sp
WHERE d.slug = 'terminal-bench'
RETURNING
    d.id AS dataset_id,
    d.slug AS dataset_slug,
    d.introducing_paper_id,
    d.introducing_paper_title,
    d.paper_url;
