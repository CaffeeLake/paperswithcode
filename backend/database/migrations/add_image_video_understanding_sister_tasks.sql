-- Link image understanding, image classification, video understanding, and
-- video classification as mutual sister tasks. Existing sisters (e.g. OCR,
-- document understanding on image-understanding) are preserved.

BEGIN;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id,
    CASE s.slug
        WHEN 'image-classification' THEN 0
        WHEN 'image-understanding' THEN 1
        WHEN 'video-classification' THEN 2
        WHEN 'video-understanding' THEN 3
    END
FROM tasks t
JOIN tasks s ON s.slug IN (
    'image-understanding',
    'image-classification',
    'video-understanding',
    'video-classification'
) AND s.id <> t.id
WHERE t.slug IN (
    'image-understanding',
    'image-classification',
    'video-understanding',
    'video-classification'
)
ON CONFLICT DO NOTHING;

COMMIT;
