-- Video matting task (Video): estimate temporally consistent alpha mattes across frames.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Matting',
    'video-matting',
    'Video matting estimates alpha mattes for foreground subjects across video frames while preserving temporal consistency. It extends [Image Matting](/tasks/image-matting) to sequences for applications such as portrait-mode video, virtual backgrounds, and compositing in film and streaming.',
    'video matting, video instance matting, portrait video matting, temporal matting, video alpha matting, omnimatte, human instance matting, one-trimap video matting, high-resolution video matting',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    'https://paperswithcode.co/images/tasks/video-matting.png',
    '[Robust High-Resolution Video Matting with Temporal Guidance](/paper/2108.11515)',
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

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, CASE WHEN s.slug = 'video-matting' THEN 0 ELSE 1 END
FROM tasks t
JOIN tasks s ON s.slug IN ('image-matting', 'video-matting') AND s.id <> t.id
WHERE t.slug IN ('image-matting', 'video-matting')
ON CONFLICT DO NOTHING;
