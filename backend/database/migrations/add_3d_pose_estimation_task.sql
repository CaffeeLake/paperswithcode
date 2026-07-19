-- 3D Pose Estimation: recover articulated 3D joint configurations from images,
-- video, depth, or 2D keypoints. This is a focused child of Pose Estimation.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '3D Pose Estimation',
    '3d-pose-estimation',
    '3D pose estimation recovers the three-dimensional locations and configuration of articulated body joints from monocular or multi-view images, video, depth observations, or detected 2D keypoints. It covers human and animal pose lifting, probabilistic pose hypotheses, and direct 3D joint prediction, and is a focused subtask of [Pose Estimation](/tasks/pose-estimation).',
    '3d pose estimation, monocular 3d pose estimation, multi-view 3d pose estimation, multiview 3d pose estimation, 3d human pose estimation, human 3d pose estimation, 3d animal pose estimation, animal 3d pose estimation, 3d pose lifting, 2d-to-3d pose, 2d to 3d pose, lifting 2d pose to 3d, 3d body pose, 3d joint estimation, 3d skeleton reconstruction',
    (SELECT area_id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    true,
    NULL,
    '[EPFL CVLab: Human Pose Estimation](https://www.epfl.ch/labs/cvlab/research/research-surv/research-surv-human-pose-estimation/)',
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

-- The requested seed paper is a canonical example and should retain a manual
-- link even if future keyword matching changes.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = '3d-pose-estimation'
WHERE p.arxiv_id = '2602.05755'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
