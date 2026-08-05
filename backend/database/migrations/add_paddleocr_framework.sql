-- Add PaddleOCR to the framework catalogue and recommend it for OCR tasks.

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES (
    'https://github.com/paddlepaddle/paddleocr',
    'PaddlePaddle',
    'PaddleOCR',
    0,
    'framework_catalog'
)
ON CONFLICT (url) DO UPDATE SET
    owner = EXCLUDED.owner,
    name = EXCLUDED.name;

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
    'paddleocr',
    'PaddleOCR',
    'PaddlePaddle',
    'A multilingual OCR and document AI toolkit for turning images and PDFs into structured data.',
    'Use it for end-to-end text detection and recognition, document parsing, and structured Markdown or JSON output.',
    'https://www.paddleocr.ai/',
    3
FROM framework_categories category
JOIN framework_domains domain
    ON domain.id = category.domain_id
    AND domain.slug = 'computer-vision'
JOIN repositories repository
    ON repository.url = 'https://github.com/paddlepaddle/paddleocr'
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

WITH platform(platform) AS (
    VALUES ('gpu'), ('cpu')
)
INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, platform.platform
FROM frameworks framework
CROSS JOIN platform
WHERE framework.slug = 'paddleocr'
ON CONFLICT DO NOTHING;

WITH recommendation(task_slug, display_order) AS (
    VALUES
        ('ocr', 3),
        ('document-understanding', 3),
        ('scene-text-recognition', 0)
)
INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT task.id, framework.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = recommendation.task_slug
JOIN frameworks framework ON framework.slug = 'paddleocr'
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

WITH recommendation(task_slug, display_order) AS (
    VALUES
        ('ocr', 3),
        ('document-understanding', 3),
        ('scene-text-recognition', 0)
)
INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = recommendation.task_slug
JOIN repositories repository
    ON repository.url = 'https://github.com/paddlepaddle/paddleocr'
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
