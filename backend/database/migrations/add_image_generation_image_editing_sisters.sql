-- Link Image generation and Image editing as sister tasks (bidirectional).

BEGIN;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'image-editing'
WHERE t.slug = 'image-generation'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'image-generation'
WHERE t.slug = 'image-editing'
ON CONFLICT DO NOTHING;

COMMIT;
