-- Add video-restoration as a sister task of video-super-resolution.
-- video-restoration already lists video-super-resolution as a sister task
-- (display_order 1); this migration adds the reverse direction.
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'video-restoration'
WHERE t.slug = 'video-super-resolution'
ON CONFLICT DO NOTHING;
