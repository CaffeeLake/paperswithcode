-- Add the TNL2K natural-language object-tracking benchmark.
--
-- TNL2K was introduced by Wang et al. at CVPR 2021 (arXiv:2103.16746).
-- The canonical protocol reports success AUC and precision on the 700-video
-- test split. Evaluation rows are curated separately.

BEGIN;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, license_name, license_url, modalities
)
SELECT
    'TNL2K',
    'Tracking by Natural Language (TNL2K)',
    'tnl2k',
    'TNL2K is a large-scale benchmark for tracking an object specified by natural language. It contains 2,000 manually annotated video sequences and 1,244,340 frames, split into 1,300 training videos and 700 test videos. The benchmark includes RGB, thermal, cartoon, and synthetic video; adversarial distractors; substantial appearance changes; and visual-only, language-only, and joint visual-language tracking protocols.',
    'A 2,000-sequence benchmark for tracking objects specified by natural language.',
    'https://sites.google.com/view/langtrackbenchmark/',
    'https://sites.google.com/view/langtrackbenchmark/',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2103.16746',
    DATE '2021-03-31',
    2021,
    'Custom',
    'https://sites.google.com/view/langtrackbenchmark/',
    '["video", "natural language", "RGB", "thermal"]'::jsonb
FROM papers p
WHERE p.arxiv_id = '2103.16746'
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
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'object-tracking'
WHERE p.arxiv_id = '2103.16746'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug = 'tnl2k'
WHERE t.slug = 'object-tracking'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'tnl2k'
JOIN metrics m ON m.name IN ('AUC', 'Precision')
WHERE t.slug = 'object-tracking'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
