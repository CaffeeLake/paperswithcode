-- Production compatibility gate:
-- Do not apply until a production source release that never selects or writes
-- tasks.is_visible is live in both current and immediate rollback slots.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM tasks
        WHERE slug = ANY(ARRAY[
            'coding',
            'other',
            'few-shot-image-classification',
            'general',
            'open-vocabulary-object-detection'
        ])
    ) THEN
        RAISE EXCEPTION 'obsolete hidden-task cleanup must run before column removal';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM tasks WHERE slug = 'safety-and-grounding'
    ) THEN
        RAISE EXCEPTION 'retained safety-and-grounding task is missing';
    END IF;
END
$$;

DROP INDEX IF EXISTS idx_tasks_is_visible;
ALTER TABLE tasks DROP COLUMN IF EXISTS is_visible;
