-- Add the classic offline 3DSSG scene-graph prediction protocol.
--
-- This leaderboard is deliberately separate from the reduced-label online
-- 3DSSG protocol: it uses class-agnostic ground-truth instances from the
-- official 3RScan/3DSSG split with 160 object classes and 26 predicates.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM tasks
        WHERE id = 455
          AND slug = '3d-scene-graph-generation'
    ) THEN
        RAISE EXCEPTION '3D Scene Graph Generation task identity precondition failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM papers
        WHERE id = 109330
          AND arxiv_id = '2004.03967'
          AND is_latest_version
          AND title = 'Learning 3D Semantic Scene Graphs from 3D Indoor Reconstructions'
    ) THEN
        RAISE EXCEPTION '3DSSG source paper identity precondition failed';
    END IF;
END
$$;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    (
        'Object Recall@5',
        'Object Recall at 5',
        'higher_is_better',
        'Percentage of ground-truth object labels recovered within the top 5 predictions for each ground-truth instance.',
        '0-100'
    ),
    (
        'Object Recall@10',
        'Object Recall at 10',
        'higher_is_better',
        'Percentage of ground-truth object labels recovered within the top 10 predictions for each ground-truth instance.',
        '0-100'
    ),
    (
        'Predicate Recall@3',
        'Predicate Recall at 3',
        'higher_is_better',
        'Percentage of ground-truth predicate labels recovered within the top 3 predictions for each ground-truth object pair.',
        '0-100'
    ),
    (
        'Predicate Recall@5',
        'Predicate Recall at 5',
        'higher_is_better',
        'Percentage of ground-truth predicate labels recovered within the top 5 predictions for each ground-truth object pair.',
        '0-100'
    ),
    (
        'Relationship Recall@50',
        'Relationship Recall at 50',
        'higher_is_better',
        'Percentage of ground-truth subject-predicate-object relationships recovered among the top 50 scene-level predictions.',
        '0-100'
    ),
    (
        'Relationship Recall@100',
        'Relationship Recall at 100',
        'higher_is_better',
        'Percentage of ground-truth subject-predicate-object relationships recovered among the top 100 scene-level predictions.',
        '0-100'
    )
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name,
    full_name,
    slug,
    description,
    short_description,
    url,
    homepage,
    parent_dataset_id,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_date,
    introduced_year,
    modalities,
    split_name,
    variant_type
)
SELECT
    '3DSSG (Full-Scene GT Instances, 160/26)',
    '3DSSG (Full-Scene Ground-Truth Instances, 160 Object Classes / 26 Predicates)',
    '3dssg-full-scene-gt-instances-160-26',
    'The classic offline 3DSSG scene-graph prediction benchmark uses the official 3RScan/3DSSG train/test split and class-agnostic ground-truth object instances. Systems classify 160 object categories and 26 relationship predicates, with object, predicate, and full subject-predicate-object relationship recall reported at protocol-specific cutoffs. Results from reduced-label or online reconstruction settings are not comparable and belong on separate leaderboards.',
    'Classic offline 3DSSG prediction on full scenes with ground-truth instances, 160 object classes, and 26 predicates.',
    'https://3dssg.github.io/',
    'https://3dssg.github.io/',
    parent.id,
    109330,
    p.title,
    'https://paperswithcode.co/paper/2004.03967',
    DATE '2020-04-08',
    2020,
    '["3D", "RGB-D", "point cloud"]'::jsonb,
    'Official 3RScan split — full-scene GT instances, 160 objects / 26 predicates',
    'variant'
FROM papers p
LEFT JOIN datasets parent ON parent.slug = '3dssg'
WHERE p.id = 109330
  AND p.arxiv_id = '2004.03967'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    parent_dataset_id = EXCLUDED.parent_dataset_id,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
VALUES (109330, 455, 'manual')
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 455, d.id, FALSE
FROM datasets d
WHERE d.slug = '3dssg-full-scene-gt-instances-160-26'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 455, d.id, m.id
FROM datasets d
CROSS JOIN metrics m
WHERE d.slug = '3dssg-full-scene-gt-instances-160-26'
  AND m.name IN (
      'Object Recall@5',
      'Object Recall@10',
      'Predicate Recall@3',
      'Predicate Recall@5',
      'Relationship Recall@50',
      'Relationship Recall@100'
  )
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
