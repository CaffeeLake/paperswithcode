-- Add a distinct 2D arbitrary-point tracking task. This is intentionally
-- separate from box-level object tracking and metric 3D point tracking.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '2D Point Tracking',
    'point-tracking',
    '2D point tracking, also called Tracking Any Point (TAP), estimates the image-plane trajectory and visibility of arbitrary query pixels across video frames, including through occlusion and reappearance. Methods may track sparse user-selected points or dense pixel grids. Unlike [Object Tracking](/tasks/object-tracking), the targets are points rather than bounding boxes, and unlike [3D Tracking](/tasks/3d-tracking), predictions remain in 2D image coordinates rather than metric camera or world space.',
    '2D point tracking, video point tracking, tracking any point, TAP-Vid, TAPVid, arbitrary point tracking, pixel tracking in video, pixel trajectory tracking, image-plane point tracking, sparse point tracking in video, dense point tracking in video, long-term 2D point tracking',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    TRUE,
    NULL,
    '[TAP-Vid: A Benchmark for Tracking Any Point in a Video](/paper/2211.03726)',
    'https://tapvid.github.io/,https://robotap.github.io/,https://pointodyssey.com/'
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
CROSS JOIN (VALUES
    ('optical-flow', 0),
    ('object-tracking', 1),
    ('3D-tracking', 2)
) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'point-tracking'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT s.id, t.id, COALESCE((
    SELECT max(existing.display_order) + 1
    FROM task_sister_tasks existing
    WHERE existing.task_id = s.id
), 0)
FROM tasks t
JOIN tasks s ON s.slug IN ('optical-flow', 'object-tracking', '3D-tracking')
WHERE t.slug = 'point-tracking'
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'point-tracking'
WHERE p.arxiv_id IN (
    '2211.03726', '2305.12998', '2306.05422', '2306.08637',
    '2307.07635', '2307.15055', '2312.00786', '2402.00847',
    '2403.13042', '2403.14548', '2407.15420', '2407.16291',
    '2410.11831', '2411.18671', '2412.04592', '2501.18487',
    '2504.05579', '2506.07310', '2507.06233', '2604.10582'
)
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Point-tracking metrics. The two TAP percentages are stored as fractions so
-- all leaderboards use one canonical 0-1 scale.
INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES
    ('AJ', 'Average Jaccard', 'higher_is_better', '0-1',
     'Average Jaccard jointly measures point localization and visibility prediction across distance thresholds.'),
    ('OA', 'Occlusion Accuracy', 'higher_is_better', '0-1',
     'Binary classification accuracy of predicted point visibility or occlusion over the evaluated trajectory frames.'),
    ('delta_avg', 'Average Position Accuracy / δ_avg^x', 'higher_is_better', '0-1',
     'Average fraction of eligible evaluated trajectory positions within the configured localization thresholds; eligibility and thresholds follow the benchmark contract.'),
    ('Survival', 'Survival Rate (50 px)', 'higher_is_better', '0-1',
     'Average fraction of the full video elapsed before the first tracking failure; failure is L2 trajectory error above 50 pixels after coordinates are normalized to 256×256.'),
    ('MTE', 'Median Trajectory Error', 'lower_is_better', 'unbounded',
     'Median Euclidean distance in pixels between predicted and ground-truth 2D trajectory positions after coordinates are normalized to 256×256.')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    scale = EXCLUDED.scale,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

-- Protocol and resolution are part of leaderboard identity. In particular,
-- do not mix the 384×512 rows reported by CoTracker/LocoTrack with 256px rows.
WITH benchmark_rows(
    name, slug, description, homepage, source_arxiv, split_name, variant_type,
    modalities, warning
) AS (
    VALUES
    (
      'TAP-Vid RGB-Stacking (STRIDED, 256×256)', 'tap-vid-rgb-s',
      'Protocol-specific TAP-Vid RGB-Stacking leaderboard for the STRIDED query protocol at 256×256 resolution. RGB-Stacking contains 50 synthetic robot-stacking videos, each 250 frames long, with ground-truth 2D point trajectories and visibility. Under STRIDED evaluation, query points are sampled at regular temporal intervals so tracks can be evaluated both before and after their query frame. Scores from FIRST-query evaluation, other TAP-Vid subsets, resolutions, or reporting scales are not directly comparable on this leaderboard.',
      'https://tapvid.github.io/', '2211.03726', 'RGB-Stacking; STRIDED; 256×256', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid DAVIS (Strided, 256px)', 'tap-vid-davis-strided-256px',
      'Protocol-specific 2D point-tracking benchmark on all 30 videos of the DAVIS 2017 validation set. Videos are evaluated at 256×256 resolution using TAP-Vid strided query mode, which initializes query points at regularly spaced frames along visible trajectories. Scores from first-query mode, other resolutions, or different DAVIS subsets are not comparable on this leaderboard.',
      'https://tapvid.github.io/', '2211.03726', 'DAVIS 2017 validation (30 videos); STRIDED; 256×256', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid Kinetics (STRIDED, 256px)', 'tap-vid-kinetics-strided-256px',
      'TAP-Vid Kinetics evaluation on 1,189 videos sampled from the Kinetics-700 validation set. Each video is evaluated as a 250-frame sequence resized to 256×256 pixels using the STRIDED query protocol, which introduces query points at regular temporal intervals while they are visible. This page must not mix FIRST-query or other-resolution results.',
      'https://tapvid.github.io/', '2211.03726', 'Kinetics-700 validation (1,189 videos); STRIDED; 256×256', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'RoboTAP (Query-First, 256×256)', 'robotap-query-first-256px',
      'RoboTAP is an evaluation-only benchmark of 265 real robot manipulation videos annotated in TAP-Vid format. This leaderboard uses the standard query-first point-tracking protocol at 256×256 resolution: each trajectory is initialized from its designated query point and evaluated on subsequent frames.',
      'https://robotap.github.io/', '2308.15975', 'evaluation (265 videos); QUERY-FIRST; 256×256', 'split',
      '["Videos"]'::jsonb, 'Do not mix STRIDED-query results, other resolutions, or other TAP-Vid subsets.'
    ),
    (
      'TAP-Vid DAVIS (QUERY-FIRST, 256×256)', 'tap-vid-davis-query-first-256px',
      'Protocol-specific 2D point-tracking benchmark on all 30 videos of the DAVIS 2017 validation set. Videos are evaluated at 256×256 resolution using TAP-Vid query-first mode, in which each query point is provided on the first frame where that point is visible and the trajectory is evaluated forward from that initialization. Scores from strided-query mode, other resolutions, or different DAVIS subsets are not comparable on this leaderboard.',
      'https://tapvid.github.io/', '2211.03726', 'DAVIS 2017 validation (30 videos); QUERY-FIRST; 256×256', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid Kinetics (QUERY-FIRST, 256px)', 'tap-vid-kinetics-query-first-256px',
      'TAP-Vid Kinetics evaluation on 1,189 videos sampled from the Kinetics-700 validation set. Each video is evaluated as a 250-frame sequence resized to 256×256 pixels using the QUERY-FIRST protocol, which initializes each query point on its first visible frame. This page must not mix STRIDED-query or other-resolution results.',
      'https://tapvid.github.io/', '2211.03726', 'Kinetics-700 validation (1,189 videos); QUERY-FIRST; 256×256', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid DAVIS (STRIDED, 384×512)', 'tap-vid-davis-strided-384x512',
      'Protocol-specific 2D point-tracking benchmark on all 30 videos of the DAVIS 2017 validation set. Videos are evaluated with model input and evaluation at 384×512 resolution using TAP-Vid STRIDED query mode, which initializes query points at regularly spaced frames along visible trajectories. Scores from query-first mode, 256px input, or different DAVIS subsets are not comparable on this leaderboard.',
      'https://tapvid.github.io/', '2211.03726', 'DAVIS 2017 validation (30 videos); STRIDED; 384×512', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid DAVIS (QUERY-FIRST, 384×512)', 'tap-vid-davis-query-first-384x512',
      'Protocol-specific 2D point-tracking benchmark on all 30 videos of the DAVIS 2017 validation set. Videos are evaluated with model input and evaluation at 384×512 resolution using TAP-Vid query-first mode, in which each query point is provided on the first frame where that point is visible and the trajectory is evaluated forward from that initialization. Scores from strided-query mode, 256×256 input/evaluation, other resolutions, or different DAVIS subsets are not comparable on this leaderboard.',
      'https://tapvid.github.io/', '2211.03726', 'DAVIS 2017 validation (30 videos); QUERY-FIRST; 384×512', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'PointOdyssey Test (Original, Query-First, 256px)', 'pointodyssey-test-256px',
      'The source-paper PointOdyssey long-term 2D point-tracking benchmark evaluates the original paper-era test split: 12 continuous synthetic videos (about 26,000 frames total; native 540×960 RGB at 30 FPS). Every trajectory with a valid annotation in frame 0 is queried in frame 0 and tracked through the full roughly 2,000-frame video. Coordinates are normalized to 256×256 for delta_avg, Median Trajectory Error, and Survival computation; Survival uses the first frame whose L2 error exceeds 50 normalized pixels. This contract is distinct from the expanded PointOdyssey v1.2 test release, which contains 13 videos.',
      'https://pointodyssey.com/', '2307.15055', 'test', 'split',
      '["Videos"]'::jsonb, 'Original paper-era 12-video test split only. Do not mix PointOdyssey v1.2 (13 videos), truncated clips, subsampled frames, or a different query protocol.'
    ),
    (
      'TAP-Vid Kinetics (STRIDED, 384×512)', 'tap-vid-kinetics-strided-384x512',
      'TAP-Vid Kinetics evaluation on 1,189 Kinetics-700 validation videos, each 250 frames, using STRIDED queries with model input and evaluation at 384×512. Scores from QUERY-FIRST, 256px, other resolutions, or other subsets are not comparable.',
      'https://tapvid.github.io/', '2211.03726', 'Kinetics-700 validation (1,189 videos); STRIDED; 384×512', 'variant',
      '["Videos"]'::jsonb, NULL
    ),
    (
      'TAP-Vid Kinetics (QUERY-FIRST, 384×512)', 'tap-vid-kinetics-query-first-384x512',
      'TAP-Vid Kinetics evaluation on 1,189 Kinetics-700 validation videos, each 250 frames, using QUERY-FIRST queries with model input and evaluation at 384×512. Scores from STRIDED, 256px, other resolutions, or other subsets are not comparable.',
      'https://tapvid.github.io/', '2211.03726', 'Kinetics-700 validation (1,189 videos); QUERY-FIRST; 384×512', 'variant',
      '["Videos"]'::jsonb, NULL
    )
), resolved AS (
    SELECT b.*, p.id AS paper_id, p.title AS paper_title
    FROM benchmark_rows b
    JOIN papers p ON p.arxiv_id = b.source_arxiv AND p.is_latest_version
)
INSERT INTO datasets (
    name, slug, description, short_description, homepage, url,
    introducing_paper_id, introducing_paper_title, paper_url,
    split_name, variant_type, modalities, warning
)
SELECT
    name, slug, description, left(description, 500), homepage, homepage,
    paper_id, paper_title, 'https://paperswithcode.co/paper/' || source_arxiv,
    split_name, variant_type, modalities, warning
FROM resolved
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    url = EXCLUDED.url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type,
    modalities = EXCLUDED.modalities,
    warning = EXCLUDED.warning,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug IN (
    'tap-vid-rgb-s',
    'tap-vid-davis-strided-256px', 'tap-vid-kinetics-strided-256px',
    'robotap-query-first-256px', 'tap-vid-davis-query-first-256px',
    'tap-vid-kinetics-query-first-256px',
    'tap-vid-davis-strided-384x512', 'tap-vid-davis-query-first-384x512',
    'pointodyssey-test-256px',
    'tap-vid-kinetics-strided-384x512',
    'tap-vid-kinetics-query-first-384x512'
)
WHERE t.slug = 'point-tracking'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug IN (
    'tap-vid-rgb-s',
    'tap-vid-davis-strided-256px', 'tap-vid-kinetics-strided-256px',
    'robotap-query-first-256px', 'tap-vid-davis-query-first-256px',
    'tap-vid-kinetics-query-first-256px',
    'tap-vid-davis-strided-384x512', 'tap-vid-davis-query-first-384x512',
    'tap-vid-kinetics-strided-384x512',
    'tap-vid-kinetics-query-first-384x512'
)
CROSS JOIN metrics m
WHERE t.slug = 'point-tracking'
  AND m.name IN ('AJ', 'OA', 'delta_avg')
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'pointodyssey-test-256px'
CROSS JOIN metrics m
WHERE t.slug = 'point-tracking'
  AND m.name IN ('delta_avg', 'Survival', 'MTE')
ON CONFLICT DO NOTHING;

-- Benchmark source papers remain durable manual task associations.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, t.id, 'manual'
FROM tasks t
JOIN task_datasets td ON td.task_id = t.id
JOIN datasets d ON d.id = td.dataset_id
WHERE t.slug = 'point-tracking'
  AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Broad TAP/point keywords also match papers whose actual output is metric 3D
-- geometry. Keep those on the separate 3D Tracking task.
DELETE FROM paper_tasks pt
USING papers p, tasks t
WHERE pt.paper_id = p.id
  AND pt.task_id = t.id
  AND pt.source = 'auto'
  AND t.slug = 'point-tracking'
  AND p.arxiv_id IN (
      '2407.05921', '2407.13337', '2504.14717', '2509.25183',
      '2510.26443'
  );

COMMIT;
