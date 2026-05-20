-- Migration: Add Biology task and consolidate the "Other" area
--
-- The previous taxonomy had a standalone "Time-series" area for just two
-- niche tasks (Time-series forecasting, Time-series classification) and an
-- almost-empty "Other" area. Consolidate everything that doesn't fit one of
-- the main modality areas (Vision, Video, Language, Audio, General) into
-- "Other":
--
--   * Add a new top-level "Biology" task under "Other" for AI-for-biology
--     work (protein structure, drug discovery, bioimage analysis, etc.).
--   * Move time-series-forecasting and time-series-classification from the
--     "Time-series" area into "Other".
--   * Drop the now-empty "Time-series" area.
--
-- The migration is idempotent: re-running it is a no-op once applied.
--
-- Created: 2026-05-19
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_biology_task_and_consolidate_other.sql

BEGIN;

-- 1. Ensure the "Other" area exists and refresh its description.
SELECT setval(
    pg_get_serial_sequence('areas', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM areas), 1)
);

INSERT INTO areas (name, description)
SELECT 'Other',
       'Research that does not fit into the main modality areas (Vision, Video, Language, Audio, General), including AI for biology, time-series modeling, and other cross-domain or niche tasks.'
WHERE NOT EXISTS (
    SELECT 1 FROM areas WHERE name = 'Other'
);

UPDATE areas
SET description = 'Research that does not fit into the main modality areas (Vision, Video, Language, Audio, General), including AI for biology, time-series modeling, and other cross-domain or niche tasks.',
    updated_at = NOW()
WHERE name = 'Other';

-- 2. Move the time-series tasks from "Time-series" into "Other".
UPDATE tasks
SET area_id = (SELECT id FROM areas WHERE name = 'Other'),
    updated_at = NOW()
WHERE slug IN ('time-series-forecasting', 'time-series-classification')
  AND area_id IS DISTINCT FROM (SELECT id FROM areas WHERE name = 'Other');

-- 3. Drop the now-empty "Time-series" area (only if no tasks reference it).
DELETE FROM areas
WHERE name = 'Time-series'
  AND NOT EXISTS (
      SELECT 1 FROM tasks WHERE tasks.area_id = areas.id
  );

-- 4. Insert the "Biology" task under "Other" if it does not already exist.
INSERT INTO tasks (name, description, slug, parent_id, area_id, level, is_visible)
SELECT 'Biology',
       'AI for biology covers machine learning applied to biological data and problems, including protein structure prediction, drug discovery, molecular property prediction, genomics, single-cell analysis, and bioimage understanding.',
       'biology',
       NULL,
       (SELECT id FROM areas WHERE name = 'Other'),
       0,
       TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM tasks WHERE slug = 'biology'
);

-- 5. Sanity report.
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

    RAISE NOTICE 'Tasks in "Other":';
    FOR rec IN
        SELECT t.name, t.slug
        FROM tasks t
        JOIN areas a ON a.id = t.area_id
        WHERE a.name = 'Other'
        ORDER BY t.name
    LOOP
        RAISE NOTICE '  % (slug=%)', rec.name, rec.slug;
    END LOOP;
END $$;

COMMIT;
