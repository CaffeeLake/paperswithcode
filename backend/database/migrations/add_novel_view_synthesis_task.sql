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
    'Novel View Synthesis',
    'novel-view-synthesis',
    'Novel view synthesis reconstructs a scene representation from one or more observed images and renders photorealistic images from previously unseen camera viewpoints. It covers neural radiance fields, point-based rendering, and Gaussian splatting approaches within [3D understanding](/tasks/3d-understanding).',
    'novel view synthesis, NVS, view synthesis, novel-view synthesis, neural rendering, radiance field, radiance fields, NeRF, gaussian splatting, 3D gaussian splatting, 3DGS, sparse-view reconstruction, sparse view synthesis, generalizable novel view synthesis',
    (SELECT area_id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    TRUE,
    NULL,
    '[3D Gaussian Splatting for Real-Time Radiance Field Rendering](/paper/2308.04079)',
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
