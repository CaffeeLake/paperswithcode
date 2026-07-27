-- Add ordered, database-backed framework recommendations to task pages.
-- Frameworks reuse the existing repositories table so GitHub star counts are
-- refreshed by the normal repository-star cron.

BEGIN;

CREATE TABLE IF NOT EXISTS task_recommended_frameworks (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, repository_id)
);

CREATE INDEX IF NOT EXISTS idx_task_recommended_frameworks_task_id
    ON task_recommended_frameworks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_recommended_frameworks_repository_id
    ON task_recommended_frameworks(repository_id);

COMMENT ON TABLE task_recommended_frameworks IS
'Ordered GitHub repositories recommended as starting points for a task. Repository metadata and stars come from repositories.';

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES
    ('https://github.com/huggingface/transformers', 'huggingface', 'transformers', 0, 'task_recommendation'),
    ('https://github.com/huggingface/pytorch-image-models', 'huggingface', 'pytorch-image-models', 0, 'task_recommendation'),
    ('https://github.com/roboflow/rf-detr', 'roboflow', 'rf-detr', 0, 'task_recommendation'),
    ('https://github.com/ultralytics/ultralytics', 'ultralytics', 'ultralytics', 0, 'task_recommendation'),
    ('https://github.com/vllm-project/vllm', 'vllm-project', 'vllm', 0, 'task_recommendation'),
    ('https://github.com/sgl-project/sglang', 'sgl-project', 'sglang', 0, 'task_recommendation'),
    ('https://github.com/paddlepaddle/paddleocr', 'PaddlePaddle', 'PaddleOCR', 0, 'task_recommendation'),
    ('https://github.com/huggingface/diffusers', 'huggingface', 'diffusers', 0, 'task_recommendation'),
    ('https://github.com/Comfy-Org/ComfyUI', 'Comfy-Org', 'ComfyUI', 0, 'task_recommendation')
ON CONFLICT (url) DO UPDATE SET
    owner = EXCLUDED.owner,
    name = EXCLUDED.name;

INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, recommendation.display_order
FROM (
    VALUES
        ('image-classification', 'https://github.com/huggingface/transformers', 0),
        ('image-classification', 'https://github.com/huggingface/pytorch-image-models', 1),
        ('object-detection', 'https://github.com/huggingface/transformers', 0),
        ('object-detection', 'https://github.com/roboflow/rf-detr', 1),
        ('object-detection', 'https://github.com/ultralytics/ultralytics', 2),
        ('ocr', 'https://github.com/huggingface/transformers', 0),
        ('ocr', 'https://github.com/vllm-project/vllm', 1),
        ('ocr', 'https://github.com/sgl-project/sglang', 2),
        ('ocr', 'https://github.com/paddlepaddle/paddleocr', 3),
        ('image-generation', 'https://github.com/huggingface/diffusers', 0),
        ('image-generation', 'https://github.com/Comfy-Org/ComfyUI', 1),
        ('image-editing', 'https://github.com/huggingface/diffusers', 0),
        ('image-editing', 'https://github.com/Comfy-Org/ComfyUI', 1)
) AS recommendation(task_slug, repository_url, display_order)
JOIN tasks task ON task.slug = recommendation.task_slug
JOIN repositories repository ON repository.url = recommendation.repository_url
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
