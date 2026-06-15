-- 3D object detection task (Vision): localize objects in 3D from LiDAR, depth, or multi-view data.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '3D object detection',
    '3d-object-detection',
    '3D object detection identifies and localizes objects with 3D bounding boxes from point clouds, depth maps, multi-view images, or fused sensor streams. It is central to [Autonomous Driving](/tasks/autonomous-driving), robotics, and augmented reality, and complements 2D [Object Detection](/tasks/object-detection) with metric scale and orientation in world space.',
    '3D object detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    'https://paperswithcode.co/images/tasks/3d-object-detection.png',
    '[nuScenes: A multimodal dataset for autonomous driving](/paper/1903.11027)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

-- 3D detection papers should not also carry the generic object-detection tag.
DELETE FROM paper_tasks pt_od
WHERE pt_od.task_id = (SELECT id FROM tasks WHERE slug = 'object-detection')
  AND EXISTS (
    SELECT 1 FROM paper_tasks pt_3d
    WHERE pt_3d.paper_id = pt_od.paper_id
      AND pt_3d.task_id = (SELECT id FROM tasks WHERE slug = '3d-object-detection')
  );
