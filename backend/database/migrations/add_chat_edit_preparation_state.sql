BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_edit_preparation_state.sql must run with search_path staging,public';
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS prepared_fork_sdk_session_id UUID,
    ADD COLUMN IF NOT EXISTS prepared_fork_sdk_project_key TEXT;

-- Preserve recoverability for edits prepared by the previous release, then
-- retire the overloaded error transport. New writes persist both values at
-- fork creation and never encode operation state in error_code.
UPDATE chat_messages AS message
SET prepared_fork_sdk_session_id =
        substring(message.error_code FROM 6)::UUID,
    prepared_fork_sdk_project_key = session.sdk_project_key,
    error_code = NULL
FROM chat_sessions AS session
WHERE message.session_id = session.id
  AND message.status = 'preparing'
  AND session.sdk_project_key IS NOT NULL
  AND message.error_code ~
      '^fork:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  AND message.prepared_fork_sdk_session_id IS NULL
  AND message.prepared_fork_sdk_project_key IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'chat_messages'::regclass
          AND conname = 'chat_messages_prepared_fork_pair_check'
    ) THEN
        ALTER TABLE chat_messages
            ADD CONSTRAINT chat_messages_prepared_fork_pair_check CHECK (
                (prepared_fork_sdk_session_id IS NULL)
                = (prepared_fork_sdk_project_key IS NULL)
            );
    END IF;
END $$;

COMMIT;
