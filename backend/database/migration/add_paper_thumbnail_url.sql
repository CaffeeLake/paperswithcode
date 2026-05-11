-- Migration: Add explicit paper thumbnail URLs.
--
-- ArXiv rows can continue to derive thumbnails from arxiv_id/version. External
-- rows can store a captured source-page thumbnail, usually served from the
-- existing thumbnail bucket through /api/thumbnails/custom/<file>.jpg.

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(1000);

COMMENT ON COLUMN papers.thumbnail_url IS
    'Optional explicit thumbnail image URL. External rows can use captured source-page thumbnails; ArXiv rows usually derive thumbnails from arxiv_id/version.';
