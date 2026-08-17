-- 3D tracking taxonomy plus the world-coordinate sparse and dense benchmarks
-- used by TrackCraft3R. Evaluation rows are curated separately through the
-- evaluation service so this migration remains idempotent catalog wiring.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '3D Tracking',
    '3D-tracking',
    '3D tracking estimates the trajectories and visibility of points or objects through time in three-dimensional scene or world coordinates. Unlike [Object Tracking](/tasks/object-tracking), which generally follows targets in the 2D image plane, 3D tracking reasons about depth, camera motion, occlusion, and motion in physical space, with both sparse point and dense per-pixel settings.',
    '3D tracking, 3D point tracking, dense 3D tracking, sparse 3D tracking, world-coordinate tracking, world coordinate tracking, world-frame tracking, world frame tracking, tracking any point in 3D, TAP-3D, 3D trajectories, 3D trajectory estimation, 4D tracking',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking](/paper/2605.12587)',
    'https://tapvid3d.github.io,https://st4rtrack.github.io'
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
    ('AJ', 'Average Jaccard', 'higher_is_better',
     'Average Jaccard jointly measures 3D point localization and visibility prediction across distance thresholds.', '0-1'),
    ('APD3D', 'Average Percentage of Points within 3D Distance', 'higher_is_better',
     'Average percentage of tracked points whose world-coordinate 3D endpoint error is below the benchmark distance thresholds.', '0-1'),
    ('OA', 'Occlusion Accuracy', 'higher_is_better',
     'Binary classification accuracy of predicted point visibility or occlusion over the evaluated trajectory frames.', '0-1')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

-- WorldTrack was established by St4RTrack from two TAPVid-3D real-world
-- sources and two synthetic sources. These rows preserve each sub-benchmark
-- separately because papers report one score triplet per source.
INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url
)
SELECT
    v.name,
    v.full_name,
    v.slug,
    v.description,
    v.short_description,
    'https://st4rtrack.github.io/',
    p.id,
    p.title,
    DATE '2025-04-17',
    2025,
    '["3D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2504.13152'
FROM (
    VALUES
        (
            'WorldTrack ADT',
            'WorldTrack - Aria Digital Twin',
            'worldtrack-adt',
            'The Aria Digital Twin portion of the WorldTrack benchmark evaluates sparse point trajectories in world coordinates on real egocentric indoor video. TrackCraft3R evaluates the first 84 frames with Sim(3) alignment and reports AJ, APD3D, and occlusion accuracy.',
            'World-coordinate sparse 3D tracking on Aria Digital Twin.'
        ),
        (
            'WorldTrack Panoptic Studio',
            'WorldTrack - Panoptic Studio',
            'worldtrack-panoptic-studio',
            'The Panoptic Studio portion of the WorldTrack benchmark evaluates sparse point trajectories in world coordinates on real multi-view human-motion video. TrackCraft3R evaluates the first 84 frames with Sim(3) alignment and reports AJ, APD3D, and occlusion accuracy.',
            'World-coordinate sparse 3D tracking on Panoptic Studio.'
        ),
        (
            'WorldTrack Dynamic Replica',
            'WorldTrack - Dynamic Replica',
            'worldtrack-dynamic-replica',
            'The Dynamic Replica portion of the WorldTrack benchmark evaluates sparse point trajectories in world coordinates on synthetic dynamic-scene video with camera and object motion. TrackCraft3R evaluates the first 84 frames with Sim(3) alignment and reports AJ, APD3D, and occlusion accuracy.',
            'World-coordinate sparse 3D tracking on Dynamic Replica.'
        ),
        (
            'WorldTrack PointOdyssey',
            'WorldTrack - PointOdyssey',
            'worldtrack-pointodyssey',
            'The PointOdyssey portion of the WorldTrack benchmark evaluates sparse point trajectories in world coordinates on long synthetic videos with naturalistic camera and object motion. TrackCraft3R evaluates the first 84 frames with Sim(3) alignment and reports AJ, APD3D, and occlusion accuracy.',
            'World-coordinate sparse 3D tracking on PointOdyssey.'
        )
) AS v(name, full_name, slug, description, short_description)
JOIN papers p ON p.arxiv_id = '2504.13152' AND p.is_latest_version
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

-- DELTA introduced Kubric3D as a dense, per-pixel 3D tracking benchmark.
INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url
)
SELECT
    'Kubric3D',
    'Kubric3D Dense 3D Tracking',
    'kubric3d',
    'Kubric3D evaluates dense per-pixel 3D trajectories and visibility on synthetic dynamic scenes. The TrackCraft3R protocol uses a held-out 50-sequence split, evaluates the first 24 frames after Sim(3) alignment, and reports AJ, APD3D, and occlusion accuracy.',
    'Dense per-pixel 3D tracking on held-out Kubric sequences.',
    'https://snap-research.github.io/DELTA/',
    p.id,
    p.title,
    DATE '2024-10-31',
    2024,
    '["3D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2410.24211'
FROM papers p
WHERE p.arxiv_id = '2410.24211' AND p.is_latest_version
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

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug IN (
    'worldtrack-adt',
    'worldtrack-panoptic-studio',
    'worldtrack-dynamic-replica',
    'worldtrack-pointodyssey',
    'kubric3d'
)
WHERE t.slug = '3D-tracking'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug IN (
    'worldtrack-adt',
    'worldtrack-panoptic-studio',
    'worldtrack-dynamic-replica',
    'worldtrack-pointodyssey',
    'kubric3d'
)
JOIN metrics m ON m.name IN ('AJ', 'APD3D', 'OA')
WHERE t.slug = '3D-tracking'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- The requested paper and canonical benchmark papers receive durable tags.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = '3D-tracking'
WHERE p.arxiv_id IN (
    '2407.05921',
    '2410.24211',
    '2504.13152',
    '2605.12587'
)
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Keep the existing 2D/video tracking taxonomy visible as a related task.
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'object-tracking'
WHERE t.slug = '3D-tracking'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = '3D-tracking'
WHERE t.slug = 'object-tracking'
ON CONFLICT DO NOTHING;

COMMIT;
