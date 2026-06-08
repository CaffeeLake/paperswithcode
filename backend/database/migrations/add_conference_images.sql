-- Add hero image fields to conferences (same pattern as tasks/methods).
--
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_conference_images.sql

BEGIN;

ALTER TABLE conferences
    ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS image_credit TEXT;

COMMENT ON COLUMN conferences.image_url IS
'Public URL for the conference hero image (e.g. /images/conferences/cvpr-2026.png).';

COMMENT ON COLUMN conferences.image_credit IS
'Optional markdown credit line shown under the conference hero image.';

UPDATE conferences
SET
    image_url = 'https://paperswithcode.co/images/conferences/cvpr-2026.png',
    image_credit = '[CVPR 2026](https://cvpr.thecvf.com/)',
    description = 'CVPR (IEEE/CVF Conference on Computer Vision and Pattern Recognition) is a flagship venue for computer vision, video understanding, and related machine learning research. Browse accepted papers from CVPR 2026 in Denver, grouped by research area and task, with code, project links, evals and Hugging Face artifacts where available.'
WHERE slug = 'cvpr-2026';

COMMIT;
