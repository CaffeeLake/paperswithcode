-- Restore the legacy 3D scene graph generation taxonomy and add the
-- protocol-specific leaderboards used by FROSS and DeWorldSG.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '3D Scene Graph Generation',
    '3d-scene-graph-generation',
    '3D Scene Graph Generation predicts a structured graph of object instances and their semantic or spatial relationships from point clouds, RGB-D sequences, or multi-view observations. Online and incremental systems additionally merge observations over time into a persistent scene-level graph for robotics, embodied perception, and augmented reality.',
    '3D scene graph generation, 3D semantic scene graph generation, 3D scene graph prediction, 3D semantic scene graph prediction, 3DSGG, 3DSSG prediction, online 3D scene graph generation, incremental 3D scene graph generation, RGB-D scene graph generation, point cloud scene graph prediction',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    TRUE,
    NULL,
    '[DeWorldSG: Depth-Aware 3D Semantic Scene Graph Generation via World-Model Priors](/paper/2607.00889)',
    'https://3dssg.github.io,https://github.com/Howardkhh/ReplicaSSG'
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

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    ('Relationship Recall', '3D Scene Graph Relationship Recall', 'higher_is_better',
     'Percentage of ground-truth subject-predicate-object triplets correctly recovered after object-instance matching.', '0-100'),
    ('Object Recall', '3D Scene Graph Object Recall', 'higher_is_better',
     'Percentage of ground-truth object instances that are correctly matched and assigned the correct object category.', '0-100'),
    ('Predicate Recall', '3D Scene Graph Predicate Recall', 'higher_is_better',
     'Percentage of ground-truth predicates correctly classified between matched object pairs, irrespective of object-category correctness.', '0-100'),
    ('Object mRecall', '3D Scene Graph Object Mean Recall', 'higher_is_better',
     'Class-balanced mean recall across object categories.', '0-100'),
    ('Predicate mRecall', '3D Scene Graph Predicate Mean Recall', 'higher_is_better',
     'Class-balanced mean recall across predicate categories.', '0-100')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url, split_name, variant_type
)
SELECT
    '3DSSG',
    '3DSSG — 20-Object / 7-Predicate Scene Graph Generation Protocol',
    '3dssg',
    '3DSSG extends 3RScan with semantic scene graphs for real-world indoor scans. This leaderboard follows the commonly used public train/test split and the 20-object, 7-predicate label mapping used by FROSS and DeWorldSG, reporting object, predicate, and relationship recall together with class-balanced object and predicate mean recall.',
    '3D scene graph generation on 3RScan using the common 20-object, 7-predicate protocol.',
    'https://3dssg.github.io/',
    p.id,
    p.title,
    DATE '2020-04-08',
    2020,
    '["3D", "RGB-D", "point cloud"]'::jsonb,
    'https://paperswithcode.co/paper/2004.03967',
    'Public test split — 20 object and 7 predicate categories',
    'variant'
FROM papers p
WHERE p.arxiv_id = '2004.03967' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    paper_url = EXCLUDED.paper_url,
    split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url, split_name, variant_type
)
SELECT
    v.name,
    v.full_name,
    v.slug,
    v.description,
    v.short_description,
    'https://github.com/Howardkhh/ReplicaSSG',
    p.id,
    p.title,
    DATE '2025-07-26',
    2025,
    '["3D", "RGB-D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2507.19993',
    v.split_name,
    'variant'
FROM (
    VALUES
      (
        'ReplicaSSG (Ground-Truth Pose)',
        'ReplicaSSG — Ground-Truth Camera-Pose Protocol',
        'replicassg-ground-truth-pose',
        'ReplicaSSG extends Replica with Visual Genome-aligned object categories and inter-object relationship annotations. This leaderboard uses the 11-scene test split and ground-truth camera trajectories; scores must not be mixed with results using estimated trajectories.',
        'ReplicaSSG 11-scene test protocol using ground-truth camera trajectories.',
        '11-scene test split — ground-truth camera trajectories'
      ),
      (
        'ReplicaSSG (ORB-SLAM3 Estimated Pose)',
        'ReplicaSSG — ORB-SLAM3 RGB-D Estimated Camera-Pose Protocol',
        'replicassg-orb-slam3-estimated-pose',
        'ReplicaSSG extends Replica with Visual Genome-aligned object categories and inter-object relationship annotations. This real-world-oriented protocol uses the 11-scene test split with RGB-D camera trajectories estimated by ORB-SLAM3; scores must not be mixed with ground-truth-pose results.',
        'ReplicaSSG 11-scene test protocol using ORB-SLAM3 RGB-D estimated trajectories.',
        '11-scene test split — ORB-SLAM3 RGB-D estimated trajectories'
      )
) AS v(name, full_name, slug, description, short_description, split_name)
JOIN papers p ON p.arxiv_id = '2507.19993' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    paper_url = EXCLUDED.paper_url,
    split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id IN ('2004.03967', '2507.19993', '2607.00889')
  AND p.is_latest_version
  AND t.slug = '3d-scene-graph-generation'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
CROSS JOIN datasets d
WHERE t.slug = '3d-scene-graph-generation'
  AND d.slug IN (
      '3dssg',
      'replicassg-ground-truth-pose',
      'replicassg-orb-slam3-estimated-pose'
  )
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
CROSS JOIN datasets d
CROSS JOIN metrics m
WHERE t.slug = '3d-scene-graph-generation'
  AND d.slug IN (
      '3dssg',
      'replicassg-ground-truth-pose',
      'replicassg-orb-slam3-estimated-pose'
  )
  AND m.name IN (
      'Relationship Recall',
      'Object Recall',
      'Predicate Recall',
      'Object mRecall',
      'Predicate mRecall'
  )
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
