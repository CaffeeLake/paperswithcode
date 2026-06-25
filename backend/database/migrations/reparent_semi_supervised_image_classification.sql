-- Reparent semi-supervised-image-classification as a subtask of image-classification.
-- Hierarchy-only change: benchmark/paper links are untouched. Idempotent.

UPDATE tasks
SET
    parent_id = (SELECT id FROM tasks WHERE slug = 'image-classification' LIMIT 1),
    level = (SELECT level + 1 FROM tasks WHERE slug = 'image-classification' LIMIT 1),
    area_id = (SELECT area_id FROM tasks WHERE slug = 'image-classification' LIMIT 1),
    description = 'Semi-supervised image classification leverages unlabelled data as well as labelled data to increase [Image Classification](/tasks/image-classification) performance.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'semi-supervised-image-classification';
