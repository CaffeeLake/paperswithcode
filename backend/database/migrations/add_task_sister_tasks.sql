-- Migration: Add explicit, ordered sister-task relationships
--
-- Creates the `task_sister_tasks` junction table so a task page can render an
-- explicitly curated list of "sister tasks" instead of falling back to every
-- visible task sharing the same `area_id`.
--
--   task_id        -> the task whose page renders the sister list
--   sister_task_id -> a task to show in that page's sister-task sidebar
--   display_order  -> ascending sort key for the rendered list (0 first)
--
-- The relation is directed and NOT automatically symmetric: configuring a
-- sister on task A's page does not imply A appears on the sister's page. A
-- self-edge is forbidden via CHECK constraint. Both columns cascade on task
-- delete to keep referential integrity.
--
-- The migration also seeds the `agents` task's sister list with
-- Coding Agents, Computer Use Agents, and Language Modeling (in that order)
-- when those task rows already exist.
--
-- Created: 2026-06-11
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_task_sister_tasks.sql

BEGIN;

CREATE TABLE IF NOT EXISTS task_sister_tasks (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    sister_task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, sister_task_id),
    CONSTRAINT task_sister_tasks_no_self_link CHECK (task_id <> sister_task_id)
);

CREATE INDEX IF NOT EXISTS idx_task_sister_tasks_task_id
    ON task_sister_tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_sister_tasks_sister_task_id
    ON task_sister_tasks(sister_task_id);

COMMENT ON TABLE task_sister_tasks IS
'Explicit, ordered sister-task relationships rendered on a task page sidebar. task_id is the page; sister_task_id is a task shown in that page''s sister list, sorted by display_order. Directed and not automatically symmetric.';

-- Seed the `agents` sister list: Coding Agents, Computer Use Agents,
-- Language Modeling (in that order), when all rows exist.
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT agents.id, sister.id, v.display_order
FROM tasks agents
CROSS JOIN (
    VALUES
        ('coding-agents', 0),
        ('computer-use-agents', 1),
        ('language-modeling', 2)
) AS v(slug, display_order)
JOIN tasks sister ON sister.slug = v.slug
WHERE agents.slug = 'agents'
ON CONFLICT DO NOTHING;

COMMIT;
