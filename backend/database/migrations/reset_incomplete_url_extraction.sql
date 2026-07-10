-- Requeue latest ArXiv papers whose official URL associations are incomplete.
-- A successful agent attempt will set urls_extracted back to TRUE, including
-- when it conclusively finds that no additional official URL exists.
UPDATE papers p
SET urls_extracted = FALSE,
    updated_at = CURRENT_TIMESTAMP
WHERE p.source = 'arxiv'
  AND p.is_latest_version = TRUE
  AND (
    NOT EXISTS (
      SELECT 1
      FROM paper_repositories pr
      WHERE pr.paper_id = p.id
        AND pr.is_official = TRUE
    )
    OR NOT EXISTS (
      SELECT 1
      FROM paper_project_pages ppp
      JOIN project_pages pp ON pp.id = ppp.project_page_id
      WHERE ppp.paper_id = p.id
        AND pp.is_official = TRUE
    )
  );
