-- Add Hugging Face dataset URL for conference pages (same pattern as datasets.hf_url).
--
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_conference_hf_url.sql

BEGIN;

ALTER TABLE conferences
    ADD COLUMN IF NOT EXISTS hf_url VARCHAR(500);

COMMENT ON COLUMN conferences.hf_url IS
'Canonical Hugging Face dataset URL for accepted-paper listings (e.g. ai-conferences/CVPR2026).';

UPDATE conferences
SET hf_url = 'https://huggingface.co/datasets/ai-conferences/CVPR2026'
WHERE slug = 'cvpr-2026';

COMMIT;
