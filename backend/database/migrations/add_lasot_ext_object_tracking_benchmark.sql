-- Add the LaSOT extension one-shot test benchmark to Object Tracking.
--
-- The 2020 journal version of the LaSOT paper introduced 150 sequences from
-- 15 classes outside the original 70-class release and ImageNet. Literature
-- commonly calls this evaluation set LaSOT-ext or LaSOTExtSub. It is modeled
-- here as a child subset of LaSOT rather than as an unrelated base dataset.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM tasks WHERE id = 320 AND slug = 'object-tracking'
    ) THEN
        RAISE EXCEPTION 'Object Tracking task identity precondition failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM datasets WHERE id = 874 AND slug = 'lasot'
    ) THEN
        RAISE EXCEPTION 'LaSOT parent dataset identity precondition failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM papers
        WHERE id = 4118
          AND arxiv_id = '2009.03465'
          AND is_latest_version
          AND title = 'LaSOT: A High-quality Large-scale Single Object Tracking Benchmark'
    ) THEN
        RAISE EXCEPTION 'LaSOT extension source paper identity precondition failed';
    END IF;

    IF (
        SELECT count(*)
        FROM metrics
        WHERE name IN ('AUC', 'Normalized Precision', 'Precision')
    ) <> 3 THEN
        RAISE EXCEPTION 'LaSOT extension canonical metric precondition failed';
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
    parent_dataset_id,
    variant_type,
    split_name,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_date,
    introduced_year,
    modalities,
    variants,
    pwc_url
)
SELECT
    'LaSOT-ext',
    'LaSOT Extension One-Shot Test Set',
    'lasot-ext',
    'LaSOT-ext is the one-shot evaluation subset added in the expanded LaSOT benchmark. It contains 150 densely annotated long-term tracking sequences from 15 object classes, with 10 sequences per class. These classes do not overlap with the original 70 LaSOT classes or ImageNet classes, enabling evaluation of single-object trackers on unseen categories.',
    'A challenging 150-sequence LaSOT test subset for one-shot evaluation on 15 unseen object classes.',
    'https://vision.cs.stonybrook.edu/~lasot/',
    'https://vision.cs.stonybrook.edu/~lasot/',
    874,
    'subset',
    'one-shot test',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2009.03465',
    DATE '2020-09-08',
    2020,
    '["Videos"]'::jsonb,
    '["LaSOT-ext", "LaSOT Extension", "LaSOTExtSub"]'::jsonb,
    'https://paperswithcode.com/sota/visual-object-tracking-on-lasot-ext'
FROM papers p
WHERE p.id = 4118
  AND p.arxiv_id = '2009.03465'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    parent_dataset_id = EXCLUDED.parent_dataset_id,
    variant_type = EXCLUDED.variant_type,
    split_name = EXCLUDED.split_name,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
VALUES (4118, 320, 'manual')
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 320, d.id, FALSE
FROM datasets d
WHERE d.slug = 'lasot-ext'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 320, d.id, m.id
FROM datasets d
CROSS JOIN metrics m
WHERE d.slug = 'lasot-ext'
  AND m.name IN ('AUC', 'Normalized Precision', 'Precision')
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
