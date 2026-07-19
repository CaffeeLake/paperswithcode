-- Exploration and Sparse Rewards was introduced locally as a synthetic RL
-- grouping rather than imported from the legacy Papers With Code taxonomy.
-- Keep its sole evaluation under the existing Atari Games task, then remove
-- the synthetic task and its broad auto-generated paper links.

BEGIN;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT e.paper_id, replacement.id, 'manual'
FROM evaluations e
JOIN tasks obsolete ON obsolete.id = e.task_id
JOIN tasks replacement ON replacement.slug = 'atari-games'
WHERE obsolete.slug = 'exploration-and-sparse-rewards'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

UPDATE evaluations e
SET task_id = replacement.id,
    updated_at = CURRENT_TIMESTAMP
FROM tasks obsolete, tasks replacement
WHERE e.task_id = obsolete.id
  AND obsolete.slug = 'exploration-and-sparse-rewards'
  AND replacement.slug = 'atari-games';

DELETE FROM task_dataset_metrics
WHERE task_id = (
    SELECT id FROM tasks WHERE slug = 'exploration-and-sparse-rewards'
);

DELETE FROM task_datasets
WHERE task_id = (
    SELECT id FROM tasks WHERE slug = 'exploration-and-sparse-rewards'
);

DELETE FROM paper_tasks
WHERE task_id = (
    SELECT id FROM tasks WHERE slug = 'exploration-and-sparse-rewards'
);

DELETE FROM task_sister_tasks
WHERE task_id = (
        SELECT id FROM tasks WHERE slug = 'exploration-and-sparse-rewards'
    )
   OR sister_task_id = (
        SELECT id FROM tasks WHERE slug = 'exploration-and-sparse-rewards'
    );

DELETE FROM tasks
WHERE slug = 'exploration-and-sparse-rewards';

COMMIT;
