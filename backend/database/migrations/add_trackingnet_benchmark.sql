-- Restore the canonical TrackingNet single-object-tracking benchmark.
--
-- TrackingNet's official evaluation reports success AUC, precision, and
-- normalized precision. Legacy rows also used "Accuracy"/"ACCURACY" as a
-- duplicate label for success AUC; those aliases are deliberately not added.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM tasks WHERE id = 320 AND slug = 'object-tracking'
    ) THEN
        RAISE EXCEPTION 'Object Tracking task identity precondition failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM papers
        WHERE id = 1190
          AND arxiv_id = '1803.10794'
          AND is_latest_version
          AND title = 'TrackingNet: A Large-Scale Dataset and Benchmark for Object Tracking in the Wild'
    ) THEN
        RAISE EXCEPTION 'TrackingNet source paper identity precondition failed';
    END IF;

    IF (
        SELECT count(*)
        FROM metrics
        WHERE name IN ('AUC', 'Precision', 'Normalized Precision')
    ) <> 3 THEN
        RAISE EXCEPTION 'TrackingNet canonical metric precondition failed';
    END IF;
END
$$;

INSERT INTO datasets (
    name,
    full_name,
    slug,
    description,
    short_description,
    url,
    homepage,
    image_url,
    thumbnail_url,
    verified_image_url,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_date,
    introduced_year,
    license_name,
    modalities,
    variants,
    pwc_url
)
SELECT
    'TrackingNet',
    'TrackingNet: A Large-Scale Dataset and Benchmark for Object Tracking in the Wild',
    'trackingnet',
    'TrackingNet is a large-scale single-object tracking dataset and benchmark containing more than 30,000 videos and 14 million dense bounding-box annotations. Its held-out test benchmark contains 511 videos and is evaluated through an online server using success AUC, precision, and normalized precision.',
    'A large-scale in-the-wild single-object tracking dataset with more than 30,000 videos and a held-out 511-video test benchmark.',
    'https://tracking-net.org/',
    'https://tracking-net.org/',
    'https://production-media.paperswithcode.com/datasets/TrackingNet-0000000310-70fd8829_Bodhk7Q.jpg',
    'https://production-media.paperswithcode.com/thumbnails/dataset/dataset-0000000310-b47bfddf_RTZZhZu.jpg',
    'https://production-media.paperswithcode.com/thumbnails/dataset-small/dataset-0000000310-45da825c.jpg',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/1803.10794',
    DATE '2018-03-28',
    2018,
    'Apache 2.0',
    '["images", "video", "tracking"]'::jsonb,
    '["TrackingNet"]'::jsonb,
    'https://paperswithcode.com/dataset/trackingnet'
FROM papers p
WHERE p.id = 1190
  AND p.arxiv_id = '1803.10794'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    image_url = EXCLUDED.image_url,
    thumbnail_url = EXCLUDED.thumbnail_url,
    verified_image_url = EXCLUDED.verified_image_url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    license_name = EXCLUDED.license_name,
    modalities = EXCLUDED.modalities,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
VALUES (1190, 320, 'manual')
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 320, d.id, FALSE
FROM datasets d
WHERE d.slug = 'trackingnet'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 320, d.id, m.id
FROM datasets d
CROSS JOIN metrics m
WHERE d.slug = 'trackingnet'
  AND m.name IN ('AUC', 'Precision', 'Normalized Precision')
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
