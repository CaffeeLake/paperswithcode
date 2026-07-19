-- Link OCR, document understanding, and image understanding as mutual sister tasks.

BEGIN;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id,
    CASE s.slug
        WHEN 'document-understanding' THEN 0
        WHEN 'image-understanding' THEN 1
        WHEN 'ocr' THEN 2
    END
FROM tasks t
JOIN tasks s ON s.slug IN (
    'ocr',
    'document-understanding',
    'image-understanding'
) AND s.id <> t.id
WHERE t.slug IN (
    'ocr',
    'document-understanding',
    'image-understanding'
)
ON CONFLICT DO NOTHING;

COMMIT;
