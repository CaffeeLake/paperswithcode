-- Mark papers that already have both official URLs as fully extracted.
-- This prevents the Modal URL agent from re-processing papers that only
-- need urls_extracted flipped after legacy/manual/HF imports.
UPDATE papers p
SET urls_extracted = TRUE,
    updated_at = CURRENT_TIMESTAMP
WHERE p.source = 'arxiv'
  AND p.is_latest_version = TRUE
  AND p.urls_extracted = FALSE
  AND EXISTS (
    SELECT 1
    FROM paper_repositories pr
    WHERE pr.paper_id = p.id
      AND pr.is_official = TRUE
  )
  AND EXISTS (
    SELECT 1
    FROM paper_project_pages ppp
    JOIN project_pages pp ON pp.id = ppp.project_page_id
    WHERE ppp.paper_id = p.id
      AND pp.is_official = TRUE
  );
