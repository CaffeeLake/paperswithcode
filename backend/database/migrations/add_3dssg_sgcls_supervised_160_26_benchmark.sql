-- Add the protocol-specific supervised 3DSSG scene-graph-classification
-- leaderboard. This is intentionally separate from the online 20-object /
-- 7-predicate 3DSSG protocol because their label spaces and metrics differ.

BEGIN;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    (
        'R@20 (Graph Constraint)',
        'Recall at 20 (Graph Constraint)',
        'higher_is_better',
        'Percentage of ground-truth scene-graph triplets recovered among the top 20 predictions when at most one predicate is retained for each ordered object pair.',
        '0-100'
    ),
    (
        'R@50 (Graph Constraint)',
        'Recall at 50 (Graph Constraint)',
        'higher_is_better',
        'Percentage of ground-truth scene-graph triplets recovered among the top 50 predictions when at most one predicate is retained for each ordered object pair.',
        '0-100'
    ),
    (
        'R@100 (Graph Constraint)',
        'Recall at 100 (Graph Constraint)',
        'higher_is_better',
        'Percentage of ground-truth scene-graph triplets recovered among the top 100 predictions when at most one predicate is retained for each ordered object pair.',
        '0-100'
    ),
    (
        'ngcR@20',
        'No-Graph-Constraint Recall at 20',
        'higher_is_better',
        'Percentage of ground-truth subject-predicate-object triplets recovered among the top 20 predictions without restricting each ordered object pair to one predicate.',
        '0-100'
    ),
    (
        'ngcR@50',
        'No-Graph-Constraint Recall at 50',
        'higher_is_better',
        'Percentage of ground-truth subject-predicate-object triplets recovered among the top 50 predictions without restricting each ordered object pair to one predicate.',
        '0-100'
    ),
    (
        'ngcR@100',
        'No-Graph-Constraint Recall at 100',
        'higher_is_better',
        'Percentage of ground-truth subject-predicate-object triplets recovered among the top 100 predictions without restricting each ordered object pair to one predicate.',
        '0-100'
    ),
    (
        'mR@20',
        'Mean Recall at 20',
        'higher_is_better',
        'Class-balanced mean scene-graph recall over predicate classes among the top 20 predictions.',
        '0-100'
    ),
    (
        'mR@50',
        'Mean Recall at 50',
        'higher_is_better',
        'Class-balanced mean scene-graph recall over predicate classes among the top 50 predictions.',
        '0-100'
    ),
    (
        'mR@100',
        'Mean Recall at 100',
        'higher_is_better',
        'Class-balanced mean scene-graph recall over predicate classes among the top 100 predictions.',
        '0-100'
    )
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    parent_dataset_id, variant_type, split_name,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, modalities
)
SELECT
    '3DSSG Scene Graph Classification (Supervised, 160/26)',
    '3DSSG — Supervised Scene Graph Classification with 160 Object and 26 Predicate Classes',
    '3dssg-scene-graph-classification-supervised-160-26',
    'The standard supervised 3DSSG scene graph classification (SGCls) protocol on the public 3RScan-derived train/test split. Given object instances, a system predicts their labels from 160 object classes and semantic relationships from 26 predicate classes. This leaderboard reports graph-constrained recall, no-graph-constraint recall, and class-balanced mean recall as percentages. It is separate from online 20-object/7-predicate 3DSSG evaluation.',
    'Supervised 3DSSG SGCls on the 160-object/26-predicate label space.',
    'https://3dssg.github.io/',
    'https://3dssg.github.io/',
    parent.id,
    'variant',
    'Public 3RScan-derived split — 160 object and 26 predicate classes',
    source_paper.id,
    source_paper.title,
    'https://paperswithcode.co/paper/2004.03967',
    DATE '2020-04-08',
    2020,
    '["3D", "point cloud", "scene graph"]'::jsonb
FROM papers source_paper
LEFT JOIN datasets parent ON parent.slug = '3dssg'
WHERE source_paper.arxiv_id = '2004.03967'
  AND source_paper.is_latest_version
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
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = '3d-scene-graph-generation'
WHERE p.arxiv_id = '2004.03967'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d
  ON d.slug = '3dssg-scene-graph-classification-supervised-160-26'
WHERE t.slug = '3d-scene-graph-generation'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d
  ON d.slug = '3dssg-scene-graph-classification-supervised-160-26'
JOIN metrics m ON m.name IN (
    'R@20 (Graph Constraint)',
    'R@50 (Graph Constraint)',
    'R@100 (Graph Constraint)',
    'ngcR@20',
    'ngcR@50',
    'ngcR@100',
    'mR@20',
    'mR@50',
    'mR@100'
)
WHERE t.slug = '3d-scene-graph-generation'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
