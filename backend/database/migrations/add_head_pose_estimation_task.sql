-- Head Pose Estimation: infer a person's head orientation from visual input.
-- This is a focused child of Pose Estimation.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Head Pose Estimation',
    'head-pose-estimation',
    'Head pose estimation infers the three-dimensional orientation, and sometimes translation, of a person''s head from an image, video frame, or 3D scan. Systems commonly predict yaw, pitch, and roll or a full 6-DoF pose for applications such as gaze analysis, attention modeling, face alignment, driver monitoring, and human-computer interaction. It is a focused subtask of [Pose Estimation](/tasks/pose-estimation).',
    'unconstrained head pose estimation, multi-person head pose estimation, 6dof head pose estimation, 6-dof head pose estimation, fine-grained head pose estimation, symmetry-aware head pose estimation, face pose estimation, head pose regression, head orientation estimation, MPHPE',
    (SELECT area_id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    true,
    NULL,
    '[Head-Pose-Estimation](https://github.com/Mostafa-Nafie/Head-Pose-Estimation)',
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

-- These papers were selected from keyword and hybrid-search candidates, then
-- manually checked to ensure they actually estimate or evaluate head pose.
-- Manual links keep the reviewed set stable across automatic keyword rebuilds.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'head-pose-estimation'
WHERE p.arxiv_id IN (
    '2512.04890', -- E(3)-Pose
    '2407.14136', -- TRGv2
    '2404.02544', -- SemiUHPE
    '2403.12960', -- FaceXFormer
    '2302.01110', -- DirectMHP
    '2204.03688', -- DAD-3DHeads
    '2202.12555', -- 6DRepNet
    '2110.10953', -- MOS
    '2012.07791', -- img2pose
    '1710.00925', -- Hopenet
    '1611.01731'  -- Deep Label Distribution Learning
)
AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';

COMMIT;
