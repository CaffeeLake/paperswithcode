-- Link Image super-resolution and Video super-resolution as sister tasks (bidirectional).

BEGIN;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'video-super-resolution'
WHERE t.slug = 'image-super-resolution'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 1
FROM tasks t
JOIN tasks s ON s.slug = 'image-super-resolution'
WHERE t.slug = 'video-super-resolution'
ON CONFLICT DO NOTHING;

COMMIT;
