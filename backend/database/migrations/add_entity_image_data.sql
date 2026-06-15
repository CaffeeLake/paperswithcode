-- DB-backed entity images.
--
-- Curated hero/figure images for tasks, methods, and conferences previously
-- lived as static files under `frontend/public/images/<entity>/<slug>.png`.
-- These columns let us store the image bytes directly on the owning row:
--
--   - image_data       (BYTEA)        -> raw image bytes (deferred in the ORM
--                                         so list queries never load the blob).
--   - image_mime_type  (VARCHAR(100)) -> small, always-loaded column that also
--                                         acts as the "row has a DB image" flag.
--
-- The existing `image_url` / `image_credit` columns are kept: `image_url` still
-- holds external source URLs for rows we don't self-host, and the API prefers
-- the DB-backed image whenever `image_mime_type` is set.
--
-- Idempotent: safe to re-run.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS image_data BYTEA NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS image_mime_type VARCHAR(100) NULL;

ALTER TABLE methods ADD COLUMN IF NOT EXISTS image_data BYTEA NULL;
ALTER TABLE methods ADD COLUMN IF NOT EXISTS image_mime_type VARCHAR(100) NULL;

ALTER TABLE conferences ADD COLUMN IF NOT EXISTS image_data BYTEA NULL;
ALTER TABLE conferences ADD COLUMN IF NOT EXISTS image_mime_type VARCHAR(100) NULL;
