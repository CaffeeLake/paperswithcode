INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'Image Dehazing',
    'image-dehazing',
    'Image dehazing recovers a clear image from an input degraded by atmospheric haze or fog, restoring visibility, contrast, and color while preserving scene structure. It is a subtask of [Image Restoration](/tasks/image-restoration) and is commonly evaluated on paired synthetic or real hazy and haze-free images.',
    'image dehazing, single image dehazing, image dehaze, dehazing, haze removal, fog removal, atmospheric haze removal',
    (SELECT area_id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    NULL,
    '[Densely Connected Pyramid Dehazing Network](https://github.com/hezhangsprinter/DCPDN)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
