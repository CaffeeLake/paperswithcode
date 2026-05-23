-- Migration: Add core Image Matching benchmarks
--
-- Adds the main image-matching benchmarks surfaced by the LoFTR, SuperGlue,
-- LightGlue, and RoMa papers, excluding IMC2022 by request.
--
-- Source-paper policy:
--   * HPatches -> arXiv:1704.05939
--   * Aachen Day-Night v1.1 -> arXiv:1707.09092
--   * InLoc -> arXiv:1803.10368
--   * WxBS -> arXiv:1504.06603
--   * MegaDepth-1500 -> LoFTR evaluation protocol, arXiv:2104.00680
--   * ScanNet-1500 already existed; this migration only normalizes its native
--     paper URL and links it to Image Matching.

BEGIN;

SELECT setval(
    pg_get_serial_sequence('datasets', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM datasets), 1)
);

SELECT setval(
    pg_get_serial_sequence('metrics', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM metrics), 1)
);

-- Metrics used by these leaderboards. Degree-bearing source labels are stored
-- with ASCII "deg" so scripts can quote them consistently.
INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES
    ('AUC@1', 'Area Under Curve at 1px/1deg threshold', 'higher_is_better', 'percentage', 'Area under the cumulative error curve up to the source-defined 1 threshold.'),
    ('AUC@3', 'Area Under Curve at 3px threshold', 'higher_is_better', 'percentage', 'Area under the cumulative homography corner-error curve up to 3 pixels.'),
    ('AUC@5', 'Area Under Curve at 5px/5deg threshold', 'higher_is_better', 'percentage', 'Area under the cumulative error curve up to the source-defined 5 threshold.'),
    ('mAA@10px', 'Mean Average Accuracy at 10px', 'higher_is_better', 'percentage', 'Mean average accuracy for image matching at a 10 pixel correspondence threshold.'),
    ('Day @0.25m/2deg', 'Day localization accuracy at 0.25m / 2deg', 'higher_is_better', 'percentage', 'Percentage of day queries localized within 0.25m and 2 degrees.'),
    ('Day @0.5m/5deg', 'Day localization accuracy at 0.5m / 5deg', 'higher_is_better', 'percentage', 'Percentage of day queries localized within 0.5m and 5 degrees.'),
    ('Day @1.0m/10deg', 'Day localization accuracy at 1.0m / 10deg', 'higher_is_better', 'percentage', 'Percentage of day queries localized within 1.0m and 10 degrees.'),
    ('Night @0.25m/2deg', 'Night localization accuracy at 0.25m / 2deg', 'higher_is_better', 'percentage', 'Percentage of night queries localized within 0.25m and 2 degrees.'),
    ('Night @0.5m/5deg', 'Night localization accuracy at 0.5m / 5deg', 'higher_is_better', 'percentage', 'Percentage of night queries localized within 0.5m and 5 degrees.'),
    ('Night @1.0m/10deg', 'Night localization accuracy at 1.0m / 10deg', 'higher_is_better', 'percentage', 'Percentage of night queries localized within 1.0m and 10 degrees.'),
    ('DUC1 @0.25m/2deg', 'InLoc DUC1 localization accuracy at 0.25m / 2deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC1 queries localized within 0.25m and 2 degrees.'),
    ('DUC1 @0.5m/5deg', 'InLoc DUC1 localization accuracy at 0.5m / 5deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC1 queries localized within 0.5m and 5 degrees.'),
    ('DUC1 @1.0m/10deg', 'InLoc DUC1 localization accuracy at 1.0m / 10deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC1 queries localized within 1.0m and 10 degrees.'),
    ('DUC2 @0.25m/2deg', 'InLoc DUC2 localization accuracy at 0.25m / 2deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC2 queries localized within 0.25m and 2 degrees.'),
    ('DUC2 @0.5m/5deg', 'InLoc DUC2 localization accuracy at 0.5m / 5deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC2 queries localized within 0.5m and 5 degrees.'),
    ('DUC2 @1.0m/10deg', 'InLoc DUC2 localization accuracy at 1.0m / 10deg', 'higher_is_better', 'percentage', 'Percentage of InLoc DUC2 queries localized within 1.0m and 10 degrees.')
ON CONFLICT (name) DO UPDATE
SET full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    scale = EXCLUDED.scale,
    description = EXCLUDED.description,
    updated_at = NOW();

WITH source_papers AS (
    SELECT arxiv_id, id, title, date_published
    FROM papers
    WHERE arxiv_id IN (
        '1704.05939',
        '1707.09092',
        '1803.10368',
        '1504.06603',
        '2104.00680'
    )
      AND is_latest_version
),
benchmark_specs AS (
    SELECT *
    FROM (VALUES
        (
            'MegaDepth-1500',
            'megadepth-1500',
            'MegaDepth-1500 is a two-view relative pose estimation benchmark for image matching, commonly evaluated with pose-error AUC at 5, 10, and 20 degrees.',
            'https://github.com/zju3dv/LoFTR',
            '2104.00680'
        ),
        (
            'HPatches',
            'hpatches',
            'HPatches is a benchmark for local image descriptors and image matching, with planar image sequences and homography-based evaluation protocols.',
            'https://hpatches.github.io/',
            '1704.05939'
        ),
        (
            'Aachen Day-Night v1.1',
            'aachen-day-night-v1-1',
            'Aachen Day-Night v1.1 is an outdoor visual localization benchmark for localizing day and night query images against a daytime 3D model.',
            'https://www.visuallocalization.net/datasets/',
            '1707.09092'
        ),
        (
            'InLoc',
            'inloc',
            'InLoc is an indoor visual localization benchmark with dense matching and view-synthesis evaluation across DUC1 and DUC2 scenes.',
            'http://www.ok.sc.e.titech.ac.jp/INLOC/',
            '1803.10368'
        ),
        (
            'WxBS',
            'wxbs',
            'WxBS is a wide-baseline stereo benchmark for image pairs with large simultaneous changes in viewpoint, illumination, sensor, or appearance.',
            'https://github.com/ducha-aiki/wxbs-descriptors-benchmark',
            '1504.06603'
        )
    ) AS v(name, slug, description, homepage, arxiv_id)
)
INSERT INTO datasets (
    name,
    slug,
    description,
    homepage,
    url,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_year,
    modalities
)
SELECT
    bs.name,
    bs.slug,
    bs.description,
    bs.homepage,
    bs.homepage,
    sp.id,
    sp.title,
    'https://paperswithcode.co/paper/' || sp.arxiv_id,
    EXTRACT(YEAR FROM sp.date_published)::INTEGER,
    '["Images"]'::jsonb
FROM benchmark_specs bs
JOIN source_papers sp ON sp.arxiv_id = bs.arxiv_id
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    homepage = EXCLUDED.homepage,
    url = EXCLUDED.url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    updated_at = NOW();

-- Normalize the existing ScanNet-1500 source URL to the native local route.
UPDATE datasets d
SET paper_url = 'https://paperswithcode.co/paper/' || p.arxiv_id,
    updated_at = NOW()
FROM papers p
WHERE d.slug = 'scannet-1500'
  AND d.introducing_paper_id = p.id
  AND p.arxiv_id IS NOT NULL
  AND d.paper_url IS DISTINCT FROM 'https://paperswithcode.co/paper/' || p.arxiv_id;

-- Manually tag source papers with Image Matching so their benchmark pages are
-- discoverable even if keyword matching is rebuilt.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id IN (
    '1704.05939',
    '1707.09092',
    '1803.10368',
    '1504.06603',
    '2104.00680',
    '1911.11763'
)
  AND p.is_latest_version
  AND t.slug = 'image-matching'
ON CONFLICT (paper_id, task_id) DO UPDATE
SET source = 'manual';

-- Link benchmarks to the Image Matching task.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug IN (
    'megadepth-1500',
    'hpatches',
    'aachen-day-night-v1-1',
    'inloc',
    'wxbs',
    'scannet-1500'
)
WHERE t.slug = 'image-matching'
ON CONFLICT (task_id, dataset_id) DO UPDATE
SET supports_harness = FALSE,
    updated_at = NOW();

-- Link metrics per benchmark.
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug IN ('megadepth-1500', 'scannet-1500')
JOIN metrics m ON m.name IN ('AUC@5', 'AUC@10', 'AUC@20')
WHERE t.slug = 'image-matching'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'hpatches'
JOIN metrics m ON m.name IN ('AUC@1', 'AUC@3', 'AUC@5', 'AUC@10')
WHERE t.slug = 'image-matching'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'aachen-day-night-v1-1'
JOIN metrics m ON m.name IN (
    'Day @0.25m/2deg',
    'Day @0.5m/5deg',
    'Day @1.0m/10deg',
    'Night @0.25m/2deg',
    'Night @0.5m/5deg',
    'Night @1.0m/10deg'
)
WHERE t.slug = 'image-matching'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'inloc'
JOIN metrics m ON m.name IN (
    'DUC1 @0.25m/2deg',
    'DUC1 @0.5m/5deg',
    'DUC1 @1.0m/10deg',
    'DUC2 @0.25m/2deg',
    'DUC2 @0.5m/5deg',
    'DUC2 @1.0m/10deg'
)
WHERE t.slug = 'image-matching'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'wxbs'
JOIN metrics m ON m.name = 'mAA@10px'
WHERE t.slug = 'image-matching'
ON CONFLICT DO NOTHING;

COMMIT;
