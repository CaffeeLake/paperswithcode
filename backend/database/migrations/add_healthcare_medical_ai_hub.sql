-- Make Healthcare the curated entry point for cross-area medical AI tasks
-- without changing their existing single-parent taxonomy relationships.

BEGIN;

UPDATE tasks
SET name = 'Healthcare & Medical AI',
    description = 'Healthcare and medical AI spans clinical agents, medical knowledge and reasoning, biomedical language systems, and multimodal clinical applications. Use this page as the field-wide entry point, then explore [Medical Question Answering](/tasks/medical-question-answering), [Medical Imaging](/tasks/medical-imaging), and [Medical Visual Question Answering](/tasks/medical-visual-question-answering) for specialized benchmarks.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'healthcare';

WITH related(slug, display_order) AS (
    VALUES
        ('medical-question-answering', 0),
        ('medical-imaging', 1),
        ('medical-visual-question-answering', 2)
)
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT healthcare.id, sister.id, related.display_order
FROM tasks healthcare
CROSS JOIN related
JOIN tasks sister ON sister.slug = related.slug
WHERE healthcare.slug = 'healthcare'
ON CONFLICT (task_id, sister_task_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
