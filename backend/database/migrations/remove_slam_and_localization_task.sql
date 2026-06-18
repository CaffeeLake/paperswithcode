-- SLAM is a method, not a task. Migrate paper tags and remove the CVPR coverage task.

INSERT INTO paper_methods (paper_id, method_id)
SELECT pt.paper_id, m.id
FROM paper_tasks pt
JOIN tasks t ON t.id = pt.task_id AND t.slug = 'slam-and-localization'
JOIN methods m ON m.slug = 'slam'
WHERE NOT EXISTS (
    SELECT 1 FROM paper_methods pm
    WHERE pm.paper_id = pt.paper_id AND pm.method_id = m.id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

DELETE FROM tasks WHERE slug = 'slam-and-localization';
