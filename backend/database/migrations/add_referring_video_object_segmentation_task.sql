INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Referring Video Object Segmentation',
    'referring-video-object-segmentation',
    'Referring video object segmentation identifies and segments the object or objects described by a natural-language expression throughout a video. It extends [Video segmentation](/tasks/video-segmentation) by replacing an initial object mask with a textual reference, requiring joint language grounding, temporal association, and pixel-level segmentation.',
    'referring video object segmentation, RVOS, R-VOS, language-guided video segmentation, language guided video segmentation, referring expression video segmentation, expression-referring video segmentation, Ref-DAVIS17, Refer-YouTube-VOS, MeViS',
    (SELECT area_id FROM tasks WHERE slug = 'video-segmentation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-segmentation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-segmentation' LIMIT 1),
    true,
    NULL,
    '[MeViS benchmark examples](/paper/2308.08544)',
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
