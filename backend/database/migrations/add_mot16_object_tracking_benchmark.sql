-- Add the MOT16 multiple-object-tracking benchmark to Object Tracking.
--
-- MOT16 is introduced by arXiv:1603.00831. The legacy Papers with Code
-- leaderboard defines MOTA, IDF1, and IDs (identity switches) for this dataset.

BEGIN;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    (
        'MOTA',
        'Multiple Object Tracking Accuracy',
        'higher_is_better',
        'CLEAR MOT accuracy combining false positives, false negatives, and identity switches; higher is better.',
        'percentage'
    ),
    (
        'IDF1',
        'ID F1 Score',
        'higher_is_better',
        'The ratio of correctly identified detections over the average number of ground-truth and computed detections; higher is better.',
        'percentage'
    ),
    (
        'IDs',
        'Identity Switches',
        'lower_is_better',
        'The number of times a tracked trajectory changes its matched ground-truth identity; lower is better.',
        'unbounded'
    )
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, license_name, license_url, modalities,
    variants, pwc_url
)
SELECT
    'MOT16',
    'Multiple Object Tracking 2016',
    'mot16',
    'MOT16 is a benchmark for multiple-person tracking in crowded public scenes. It contains 14 challenging real-world video sequences, split evenly between training and test, with consistently annotated pedestrian trajectories, visibility levels, and additional object classes. The benchmark standardizes evaluation of multi-object trackers using metrics including Multiple Object Tracking Accuracy (MOTA), identity-aware IDF1, and the number of identity switches (IDs).',
    'A 14-sequence benchmark for multiple-person tracking with seven training and seven test videos.',
    'https://motchallenge.net/data/MOT16/',
    'https://motchallenge.net/data/MOT16/',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/1603.00831',
    DATE '2016-03-02',
    2016,
    'CC BY-NC-SA 3.0',
    'https://motchallenge.net/',
    '["Images", "Videos"]'::jsonb,
    '["MOT16"]'::jsonb,
    'https://paperswithcode.com/dataset/mot16'
FROM papers p
WHERE p.arxiv_id = '1603.00831'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    license_name = EXCLUDED.license_name,
    license_url = EXCLUDED.license_url,
    modalities = EXCLUDED.modalities,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id = '1603.00831'
  AND p.is_latest_version
  AND t.id = 320
  AND t.slug = 'object-tracking'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
CROSS JOIN datasets d
WHERE t.id = 320
  AND t.slug = 'object-tracking'
  AND d.slug = 'mot16'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
CROSS JOIN datasets d
CROSS JOIN metrics m
WHERE t.id = 320
  AND t.slug = 'object-tracking'
  AND d.slug = 'mot16'
  AND m.name IN ('MOTA', 'IDF1', 'IDs')
ON CONFLICT DO NOTHING;

COMMIT;
