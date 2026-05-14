-- Migration: Reorganize task areas by modality
--
-- Frontend `/tasks` (TagsIndexView) renders one section per `Area`. This
-- migration rewrites the canonical area taxonomy to be modality-shaped:
--
--   * Renames "Computer Vision" -> "Vision" (drops the explicit "videos"
--     framing in the description because video tasks now live in their own
--     area below).
--   * Renames "Natural Language Processing" -> "Language".
--   * Creates a new "Video" area for the video-modality tasks.
--   * Moves `video-classification`, `video-generation`, and `video-segmentation`
--     from Vision -> Video.
--   * Moves `ocr` from Vision -> General (OCR straddles vision + language and
--     fits better with the general/multimodal tasks).
--
-- Created: 2026-05-13
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/reorganize_task_areas.sql

BEGIN;

-- 1. Rename existing areas and refresh their descriptions.
UPDATE areas
SET name = 'Vision',
    description = 'Research on enabling machines to interpret and understand still images, including image classification, generation, editing, segmentation, detection, depth, and 3D understanding.',
    updated_at = NOW()
WHERE name = 'Computer Vision';

UPDATE areas
SET name = 'Language',
    description = 'Research on understanding and generating human language, including machine translation, text classification, and other NLP tasks (note: language modeling lives under General).',
    updated_at = NOW()
WHERE name = 'Natural Language Processing';

-- 2. Create the Video area if it does not already exist.
-- The autoincrement sequence may be behind the actual MAX(id) (gaps from prior
-- deletes), so resync it before inserting.
SELECT setval(
    pg_get_serial_sequence('areas', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM areas), 1)
);

INSERT INTO areas (name, description)
SELECT 'Video',
       'Research on understanding, classifying, segmenting, and generating video, including temporal modeling across frames.'
WHERE NOT EXISTS (
    SELECT 1 FROM areas WHERE name = 'Video'
);

-- 3. Move the video tasks from Vision to Video.
UPDATE tasks
SET area_id = (SELECT id FROM areas WHERE name = 'Video'),
    updated_at = NOW()
WHERE slug IN ('video-classification', 'video-generation', 'video-segmentation');

-- 4. Move OCR from Vision to General.
UPDATE tasks
SET area_id = (SELECT id FROM areas WHERE name = 'General'),
    updated_at = NOW()
WHERE slug = 'ocr';

-- 5. Move modality-shaped understanding tasks out of General.
UPDATE tasks
SET area_id = (SELECT id FROM areas WHERE name = 'Vision'),
    updated_at = NOW()
WHERE slug = 'image-understanding';

UPDATE tasks
SET area_id = (SELECT id FROM areas WHERE name = 'Video'),
    updated_at = NOW()
WHERE slug = 'video-understanding';

-- 6. Sanity report.
DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE 'Final area taxonomy:';
    FOR rec IN
        SELECT a.name AS area_name, COUNT(t.id) AS task_count
        FROM areas a
        LEFT JOIN tasks t ON t.area_id = a.id
        GROUP BY a.id, a.name
        ORDER BY a.name
    LOOP
        RAISE NOTICE '  % -> % tasks', rec.area_name, rec.task_count;
    END LOOP;
END $$;

COMMIT;
