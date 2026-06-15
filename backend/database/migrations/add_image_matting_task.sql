-- Image matting task (Vision): estimate soft alpha mattes for foreground/background separation.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Image Matting',
    'image-matting',
    'Image matting estimates a soft alpha matte that separates foreground subjects from the background, producing per-pixel opacity for natural compositing. Unlike hard [Image Segmentation](/tasks/image-segmentation), matting models fractional transparency at object boundaries and is central to photo editing, film VFX, and virtual backgrounds.',
    'image matting, alpha matting, natural image matting, portrait matting, trimap-free matting, trimap-free portrait matting, background matting, human matting',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    'https://paperswithcode.co/images/tasks/image-matting.png?v=20260614',
    '[Accurate Alpha Matting for Portrait Mode Selfies on Pixel 6](https://research.google/blog/accurate-alpha-matting-for-portrait-mode-selfies-on-pixel-6/)',
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
