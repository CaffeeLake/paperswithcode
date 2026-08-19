INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    is_visible,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    '3D Reconstruction',
    '3d-reconstruction',
    '3D reconstruction recovers a geometric model of a scene or object — camera poses, sparse points, dense depth, meshes, or implicit surfaces — from one or more images. It covers structure-from-motion, multi-view stereo, and learning-based MVS within [3D understanding](/tasks/3d-understanding), and is complementary to [Stereo Matching](/tasks/stereo-matching), [Image Matching](/tasks/image-matching), [Camera Pose Estimation](/tasks/camera-pose-estimation), and [Novel View Synthesis](/tasks/novel-view-synthesis).',
    '3d reconstruction, 3D reconstruction, structure-from-motion, structure from motion, SfM, multi-view stereo, multiview stereo, multi view stereo, MVS, MVSNet, COLMAP, photogrammetry, bundle adjustment, dense reconstruction',
    (SELECT area_id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    TRUE,
    NULL,
    '[MVSNet: Depth Inference for Unstructured Multi-view Stereo](/paper/1804.02505)',
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
