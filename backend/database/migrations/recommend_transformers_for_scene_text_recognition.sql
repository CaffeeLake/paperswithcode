-- Recommend Hugging Face Transformers for scene text recognition.

BEGIN;

WITH recommendation(framework_slug, display_order) AS (
    VALUES
        ('transformers-vision', 0),
        ('paddleocr', 1)
)
INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT task.id, framework.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = 'scene-text-recognition'
JOIN frameworks framework ON framework.slug = recommendation.framework_slug
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

WITH recommendation(repository_url, display_order) AS (
    VALUES
        ('https://github.com/huggingface/transformers', 0),
        ('https://github.com/paddlepaddle/paddleocr', 1)
)
INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = 'scene-text-recognition'
JOIN repositories repository ON repository.url = recommendation.repository_url
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
