-- Frontend v2 migration: schema additions on `papers`.
--
-- Two new nullable columns to back UI surfaces in `frontend_v2`:
--
--   - tldr       (TEXT)    -> "TL;DR · AI-generated" panel on PaperDetailView. The panel
--                            is hidden when null. No generation pipeline is added in this
--                            migration; a follow-up workstream owns that.
--   - num_pages  (INTEGER) -> Source-PDF page count. Schema-only; not surfaced in the UI
--                            yet (the v2 PdfThumbnail mock had a `pdfPages` field, but the
--                            real PaperThumbnail replaces it). Follow-up ingestion can fill
--                            this from PyMuPDF inside the existing extract_urls.py CRON.
--
-- Idempotent: safe to re-run.

ALTER TABLE papers ADD COLUMN IF NOT EXISTS tldr TEXT NULL;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS num_pages INTEGER NULL;
