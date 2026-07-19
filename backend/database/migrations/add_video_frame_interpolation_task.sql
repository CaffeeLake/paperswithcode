BEGIN;

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
    'Video frame interpolation',
    'video-frame-interpolation',
    'Video frame interpolation synthesizes one or more temporally intermediate frames between input video frames, increasing frame rate or creating slow motion while preserving motion, appearance, and temporal consistency. It spans flow-based, kernel-based, and generative approaches and is closely related to [Video super-resolution](/tasks/video-super-resolution) and [Video Restoration](/tasks/video-restoration).',
    'video frame interpolation, frame interpolation, VFI, intermediate frame synthesis, video interpolation, arbitrary-timestep frame interpolation',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[RIFE: Real-Time Intermediate Flow Estimation for Video Frame Interpolation](/paper/2011.06294)',
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

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'video-frame-interpolation'
WHERE p.arxiv_id = '2011.06294'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';

-- RIFE estimates task-specific intermediate flows but does not evaluate optical
-- flow. Its previous Optical Flow tag came from an abstract keyword match.
DELETE FROM paper_tasks pt
USING papers p, tasks t
WHERE pt.paper_id = p.id
  AND pt.task_id = t.id
  AND p.arxiv_id = '2011.06294'
  AND t.slug = 'optical-flow'
  AND pt.source = 'auto';

COMMIT;
