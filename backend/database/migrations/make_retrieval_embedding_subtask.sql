-- Migration: Make `retrieval` a first-class subtask of `embedding-models`
--
-- Mirrors the subtask model introduced for `language-modeling` in
-- `add_language_modeling_subtasks.sql`. The `retrieval` task already owns its
-- own `task_datasets`, `task_dataset_metrics`, and `evaluations`, so the only
-- change required is to reparent it under `embedding-models` and clear its
-- `area_id` so it no longer appears as a top-level card on `/tasks`.
--
-- Idempotent: re-running this migration after a successful apply is a no-op
-- (the UPDATE matches against the resolved parent id, level, and NULL
-- area_id).
--
-- Created: 2026-05-14
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/make_retrieval_embedding_subtask.sql

BEGIN;

DO $$
DECLARE
    v_parent_id    INTEGER;
    v_parent_level INTEGER;
    v_child_id     INTEGER;
BEGIN
    SELECT id, level INTO v_parent_id, v_parent_level
    FROM tasks
    WHERE slug = 'embedding-models';

    IF v_parent_id IS NULL THEN
        RAISE EXCEPTION 'Parent task `embedding-models` not found';
    END IF;

    SELECT id INTO v_child_id
    FROM tasks
    WHERE slug = 'retrieval';

    IF v_child_id IS NULL THEN
        RAISE EXCEPTION 'Child task `retrieval` not found';
    END IF;

    UPDATE tasks
    SET parent_id  = v_parent_id,
        level      = v_parent_level + 1,
        area_id    = NULL,
        updated_at = NOW()
    WHERE id = v_child_id;

    RAISE NOTICE
        'Reparented retrieval (id=%) under embedding-models (id=%, level=%)',
        v_child_id, v_parent_id, v_parent_level;
END $$;

COMMIT;
