-- Add the NT-VOT211 night-time single-object-tracking benchmark.
--
-- NT-VOT211 was introduced at ACCV 2024 (arXiv:2410.20421). Its common
-- one-pass evaluation reports success AUC and center-error precision. The
-- legacy PwC table contains 43 trackers; evaluation rows are curated
-- separately.

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
        WHERE arxiv_id = '2410.20421'
          AND is_latest_version
          AND title = 'NT-VOT211: A Large-Scale Benchmark for Night-time Visual Object Tracking'
    ) THEN
        RAISE EXCEPTION 'NT-VOT211 source paper identity precondition failed';
    END IF;

    IF (
        SELECT count(*) FROM metrics WHERE name IN ('AUC', 'Precision')
    ) <> 2 THEN
        RAISE EXCEPTION 'NT-VOT211 canonical metric precondition failed';
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
    license_url,
    modalities,
    languages,
    variants,
    pwc_url
)
SELECT
    'NT-VOT211',
    'NT-VOT211: A Large-Scale Benchmark for Night-time Visual Object Tracking',
    'nv-vot211',
    'NT-VOT211 is a night-time single-object-tracking benchmark containing 211 diverse videos and 211,000 annotated frames. Its eight frame-level attributes cover camera motion, deformation, fast motion, motion blur, tiny targets, distractors, occlusion, and targets moving out of view. The benchmark uses one-pass evaluation and provides public and private evaluation-server phases.',
    'A night-time single-object-tracking benchmark with 211 videos, 211,000 annotated frames, and eight challenge attributes.',
    'https://github.com/LiuYuML/NT-VOT211',
    'https://github.com/LiuYuML/NT-VOT211',
    'https://production-media.paperswithcode.com/datasets/a289b312-86bc-47f9-8c07-e327099d8506.png',
    'https://production-media.paperswithcode.com/thumbnails/dataset/1ac2a2e5-e29f-4ec1-80a0-4d6f3ff6bb33.jpg',
    'https://production-media.paperswithcode.com/thumbnails/dataset-small/a9d96fdb-369e-4e35-9dd5-d2bfe1c0dc76.jpg',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2410.20421',
    DATE '2024-10-27',
    2024,
    'MIT',
    'https://github.com/LiuYuML/NT-VOT211/blob/main/LICENSE',
    '["images", "video", "tracking"]'::jsonb,
    '["English"]'::jsonb,
    '["NT-VOT211"]'::jsonb,
    'https://paperswithcode.com/dataset/nv-vot211'
FROM papers p
WHERE p.arxiv_id = '2410.20421'
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
    license_url = EXCLUDED.license_url,
    modalities = EXCLUDED.modalities,
    languages = EXCLUDED.languages,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, 320, 'manual'
FROM papers p
WHERE p.arxiv_id = '2410.20421'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 320, d.id, FALSE
FROM datasets d
WHERE d.slug = 'nv-vot211'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 320, d.id, m.id
FROM datasets d
CROSS JOIN metrics m
WHERE d.slug = 'nv-vot211'
  AND m.name IN ('AUC', 'Precision')
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
