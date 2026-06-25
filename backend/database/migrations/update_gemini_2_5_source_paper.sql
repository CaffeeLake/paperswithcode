-- Align Gemini 2.5 method source metadata with its canonical source paper.
-- source_paper_id was set to arXiv:2507.06261 but source_title/source_url still
-- pointed at the old Gemini 2.0 Google docs entry.

UPDATE methods
SET
    source_url = NULL,
    source_title = (
        SELECT title
        FROM papers
        WHERE arxiv_id = '2507.06261'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gemini-2-5';
