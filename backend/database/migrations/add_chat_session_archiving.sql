BEGIN;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_active_updated
    ON chat_sessions (hf_user_id, updated_at DESC, id DESC)
    WHERE archived_at IS NULL;

COMMIT;
