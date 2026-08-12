INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, languages, modalities
)
SELECT
    'PutnamBench',
    'PutnamBench',
    'putnambench',
    'A multilingual formal theorem-proving benchmark containing 640 competition mathematics problems from the William Lowell Putnam Mathematical Competition, formalized in Lean 4, Isabelle, and Coq.',
    'Formal theorem proving on 640 undergraduate competition mathematics problems.',
    'https://github.com/trishullab/PutnamBench',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2407.11214',
    DATE '2024-07-15',
    2024,
    '["English"]'::jsonb,
    '["Text"]'::jsonb
FROM papers p
WHERE p.arxiv_id = '2407.11214' AND p.is_latest_version
LIMIT 1
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    languages = EXCLUDED.languages,
    modalities = EXCLUDED.modalities,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, languages, modalities
)
SELECT
    'Omni-MATH',
    'Omni-MATH',
    'omni-math',
    'A benchmark of 4,428 rigorously annotated Olympiad-level mathematics problems spanning more than 33 subdomains and 10 difficulty levels for evaluating large language model reasoning.',
    'Olympiad-level mathematical reasoning across 4,428 annotated problems.',
    'https://github.com/KbsdJames/Omni-MATH',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2410.07985',
    DATE '2024-10-10',
    2024,
    '["English"]'::jsonb,
    '["Text"]'::jsonb
FROM papers p
WHERE p.arxiv_id = '2410.07985' AND p.is_latest_version
LIMIT 1
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    languages = EXCLUDED.languages,
    modalities = EXCLUDED.modalities,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id IN ('2407.11214', '2410.07985')
  AND p.is_latest_version
  AND t.slug = 'math'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
CROSS JOIN datasets d
WHERE t.slug = 'math'
  AND d.slug IN ('putnambench', 'omni-math')
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN (VALUES
    ('putnambench', 'Pass Rate'),
    ('omni-math', 'Accuracy')
) AS requested(dataset_slug, metric_name) ON TRUE
JOIN datasets d ON d.slug = requested.dataset_slug
JOIN metrics m ON m.name = requested.metric_name
WHERE t.slug = 'math'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

UPDATE tasks
SET keywords = concat_ws(', ', NULLIF(keywords, ''), 'putnambench'),
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'math'
  AND COALESCE(keywords, '') !~* '(^|,\s*)putnambench(\s*,|$)';

UPDATE tasks
SET keywords = concat_ws(', ', NULLIF(keywords, ''), 'omni-math'),
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'math'
  AND COALESCE(keywords, '') !~* '(^|,\s*)omni-math(\s*,|$)';
