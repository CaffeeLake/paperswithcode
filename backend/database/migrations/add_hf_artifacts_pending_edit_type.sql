-- Migration: allow hf_artifacts pending paper edits
--
-- Extends the pending_paper_edits edit_type check constraint so non-admin
-- users can submit Hugging Face artifact link changes for admin review.
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
            'hf_artifacts'
        )
    );

COMMIT;
