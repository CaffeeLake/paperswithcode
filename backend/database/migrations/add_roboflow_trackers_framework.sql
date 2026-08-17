-- Add Roboflow Trackers to the framework catalogue and recommend it for object tracking.

BEGIN;

INSERT INTO frameworks (
    category_id,
    repository_id,
    slug,
    name,
    organization_name,
    description,
    when_to_use,
    docs_url,
    display_order
)
SELECT
    category.id,
    repository.id,
    'roboflow-trackers',
    'Trackers',
    'Roboflow',
    'A detector-agnostic Python library with clean, benchmarked implementations of leading multi-object tracking algorithms behind one consistent interface.',
    'Use it to add, compare, tune, and evaluate multi-object trackers with an existing detector, from research benchmarks to production video pipelines.',
    'https://trackers.roboflow.com/',
    4
FROM framework_categories category
JOIN framework_domains domain
    ON domain.id = category.domain_id
    AND domain.slug = 'computer-vision'
JOIN repositories repository
    ON repository.url = 'https://github.com/roboflow/trackers'
WHERE category.slug = 'vision-model-libraries'
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, 'cpu'
FROM frameworks framework
WHERE framework.slug = 'roboflow-trackers'
ON CONFLICT DO NOTHING;

INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT task.id, framework.id, 0
FROM tasks task
JOIN frameworks framework ON framework.slug = 'roboflow-trackers'
WHERE task.slug = 'object-tracking'
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, 0
FROM tasks task
JOIN repositories repository
    ON repository.url = 'https://github.com/roboflow/trackers'
WHERE task.slug = 'object-tracking'
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
