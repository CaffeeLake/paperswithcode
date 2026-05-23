-- Migration: Add Image Matching task under the Vision area
--
-- Image matching covers local feature matching, correspondence estimation,
-- homography estimation, and relative pose evaluation benchmarks such as
-- HPatches, ScanNet-1500, Aachen Day-Night, and InLoc.
--
-- Idempotent: re-running this migration leaves an existing image-matching
-- task in place and refreshes its Vision assignment/visibility.

BEGIN;

SELECT setval(
    pg_get_serial_sequence('tasks', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM tasks), 1)
);

INSERT INTO tasks (
    name,
    description,
    slug,
    parent_id,
    area_id,
    level,
    keywords,
    is_visible
)
SELECT
    'Image Matching',
    'Image matching is the computer vision task of finding corresponding points, regions, or features across images, supporting applications such as homography estimation, relative pose estimation, structure from motion, and visual localization.',
    'image-matching',
    NULL,
    (SELECT id FROM areas WHERE name = 'Vision'),
    0,
    'local feature matching, feature correspondence, image correspondence, homography estimation, relative pose estimation, visual localization, keypoint matching, detector-free matching',
    TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM tasks WHERE slug = 'image-matching'
);

UPDATE tasks
SET name = 'Image Matching',
    description = 'Image matching is the computer vision task of finding corresponding points, regions, or features across images, supporting applications such as homography estimation, relative pose estimation, structure from motion, and visual localization.',
    parent_id = NULL,
    area_id = (SELECT id FROM areas WHERE name = 'Vision'),
    level = 0,
    keywords = 'local feature matching, feature correspondence, image correspondence, homography estimation, relative pose estimation, visual localization, keypoint matching, detector-free matching',
    is_visible = TRUE,
    updated_at = NOW()
WHERE slug = 'image-matching';

COMMIT;
