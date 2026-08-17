-- Add immutable primary-paper binding and per-turn reader context.
-- Apply with search_path=staging,public or public before activating code that
-- uses the shared chat ORM.

BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_primary_paper.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS primary_paper_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chat_sessions_primary_paper_id_fkey'
          AND conrelid = 'chat_sessions'::regclass
    ) THEN
        ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_primary_paper_id_fkey
            FOREIGN KEY (primary_paper_id)
            REFERENCES public.papers(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_paper_updated
    ON chat_sessions (hf_user_id, primary_paper_id, updated_at DESC, id DESC)
    WHERE archived_at IS NULL AND primary_paper_id IS NOT NULL;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS primary_paper_context JSONB;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS viewer_context JSONB;

COMMIT;
