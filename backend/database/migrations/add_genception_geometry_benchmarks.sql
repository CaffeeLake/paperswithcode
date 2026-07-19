-- Add the geometry task taxonomy and benchmark wiring used by GenCeption.
--
-- This migration intentionally adds no evaluation rows and leaves all new
-- task/dataset links unfeatured.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES
(
    'Surface Normal Estimation',
    'surface-normal-estimation',
    'Surface normal estimation predicts a three-dimensional orientation vector for each visible surface point in an image or video, providing local scene geometry for reconstruction, relighting, and spatial understanding. It complements [Depth estimation](/tasks/depth-estimation), which estimates distance rather than orientation.',
    'surface normal estimation, surface normals, normal estimation, normal prediction, monocular surface normals, video surface normals, per-pixel normals',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Video Generation Models are General-Purpose Vision Learners](/paper/2607.09024)',
    NULL
),
(
    'Camera Pose Estimation',
    'camera-pose-estimation',
    'Camera pose estimation recovers a camera''s position and orientation from images or video, either in a global coordinate frame or relative to neighboring frames. It supports visual localization, mapping, reconstruction, and [Novel View Synthesis](/tasks/novel-view-synthesis).',
    'camera pose estimation, camera pose, camera localization, camera trajectory estimation, camera motion estimation, relative camera pose, absolute camera pose, visual odometry, ATE, RPE',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Video Generation Models are General-Purpose Vision Learners](/paper/2607.09024)',
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

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    ('mAE', 'Mean Angular Error', 'lower_is_better',
     'Mean angular error between predicted and ground-truth surface normals; lower is better.', 'unbounded'),
    ('ATE', 'Average Translation Error', 'lower_is_better',
     'Average camera translation error over an evaluated sequence; lower is better.', 'unbounded'),
    ('RPE-T', 'Relative Pose Error - Translation', 'lower_is_better',
     'Translational component of relative camera pose error; lower is better.', 'unbounded'),
    ('RPE-R', 'Relative Pose Error - Rotation', 'lower_is_better',
     'Rotational component of relative camera pose error; lower is better.', 'unbounded')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url
)
SELECT
    'Hi4D',
    'Hi4D: 4D Instance Segmentation of Close Human Interaction',
    'hi4d',
    'Hi4D is a dataset of high-quality 4D textured scans of closely interacting people, with instance-level geometry and correspondence annotations. GenCeption follows the established held-out sequence protocol to evaluate surface normal estimation.',
    '4D textured scans of people in close physical interaction.',
    'https://yifeiyin04.github.io/Hi4D/',
    p.id,
    p.title,
    DATE '2023-03-27',
    2023,
    '["3D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2303.15380'
FROM papers p
WHERE p.arxiv_id = '2303.15380' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    paper_url = EXCLUDED.paper_url,
    updated_at = CURRENT_TIMESTAMP;

-- Normalize Sintel's already-existing native source provenance.
UPDATE datasets d
SET introducing_paper_id = p.id,
    introducing_paper_title = p.title,
    paper_url = 'https://paperswithcode.co/paper/' || p.id,
    updated_at = CURRENT_TIMESTAMP
FROM papers p
WHERE d.slug = 'sintel'
  AND p.id = 85620
  AND p.title = 'A Naturalistic Open Source Movie for Optical Flow Evaluation';

-- Benchmark-source papers receive durable task tags.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.id = 85620
  AND t.slug IN ('surface-normal-estimation', 'camera-pose-estimation')
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id = '2303.15380'
  AND p.is_latest_version
  AND t.slug = 'surface-normal-estimation'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Leave featured_rank NULL: these are ordinary, unpinned task benchmarks.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON (
    (t.slug = 'surface-normal-estimation' AND d.slug IN ('sintel', 'hi4d'))
    OR (t.slug = 'camera-pose-estimation' AND d.slug = 'sintel')
)
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug IN ('sintel', 'hi4d')
JOIN metrics m ON m.name = 'mAE'
WHERE t.slug = 'surface-normal-estimation'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'sintel'
JOIN metrics m ON m.name IN ('ATE', 'RPE-T', 'RPE-R')
WHERE t.slug = 'camera-pose-estimation'
ON CONFLICT DO NOTHING;

COMMIT;
