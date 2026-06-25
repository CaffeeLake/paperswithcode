-- Video restoration task (Video): recover clean video from degraded inputs.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Restoration',
    'video-restoration',
    'Video restoration recovers clean video from degraded inputs such as noise, blur, compression artifacts, rain, or haze while preserving temporal consistency across frames. Methods span classical optimization, deep video denoisers/deblurrers, and generative one-step or diffusion-based restorers, complementing [Image Restoration](/tasks/image-restoration) and [Video super-resolution](/tasks/video-super-resolution).',
    'video restoration, video deblurring, video deraining, video dehazing, blind video restoration, generative video restoration, temporal video restoration, video enhancement, video quality enhancement, streaming video restoration',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[SwiftVR: Real-Time One-Step Generative Video Restoration](/paper/2606.09516)',
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
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('image-restoration', 0), ('video-super-resolution', 1)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'video-restoration'
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'video-restoration'
WHERE p.arxiv_id = '2606.09516'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
