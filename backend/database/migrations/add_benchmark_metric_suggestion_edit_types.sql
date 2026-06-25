-- Migration: allow new_benchmark / new_metric suggestion pending paper edits
--
-- Extends the pending_paper_edits edit_type check constraint so signed-in
-- users can suggest brand-new benchmarks or metrics from the evaluation edit
-- dialog on a paper page. These suggestions are paper-scoped and carry a
-- {"name": ..., "description": ...} payload. Approval/rejection only updates
-- the row status; nothing is auto-created (admins create the benchmark/metric
-- and its leaderboard manually).
--
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE pending_paper_edits
    DROP CONSTRAINT IF EXISTS pending_paper_edits_edit_type_check;

ALTER TABLE pending_paper_edits
    ADD CONSTRAINT pending_paper_edits_edit_type_check CHECK (
        edit_type IN (
            'tasks',
            'methods',
            'evaluations',
            'repositories',
            'project_pages',
            'source_url',
            'hf_artifacts',
            'new_task',
            'new_method',
            'new_benchmark',
            'new_metric'
        )
    );

COMMIT;
