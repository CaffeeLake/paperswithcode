-- Migration: Add `is_visible` column to tasks
-- Description: Controls whether a task is surfaced in user-facing task pickers
--              (the public `/tasks` taxonomy and the paper task-tagging
--              dropdown). Hidden tasks still exist and remain reachable
--              by direct URL/slug, but no longer appear as selectable
--              options or as cards in the taxonomy index.
-- Date: 2026-05-19

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT TRUE;

-- Initial denylist: matches the previously hardcoded frontend hide lists
-- in TagsIndexView (`/tasks` page) and TagBrowseView (subtask grids).
UPDATE tasks
SET is_visible = FALSE
WHERE slug IN (
    'few-shot-image-classification',
    'object-counting',
    'open-vocabulary-object-detection',
    'other',
    'classic-language-modeling',
    'coding',
    'safety-and-grounding'
);

CREATE INDEX IF NOT EXISTS idx_tasks_is_visible ON tasks(is_visible);

COMMENT ON COLUMN tasks.is_visible IS
'Whether this task appears in user-facing pickers (the /tasks taxonomy index and the paper-tagging dropdown). Hidden tasks still exist and are reachable by direct slug/id.';
