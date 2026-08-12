BEGIN;

-- This additive migration is intentionally confined to the protected staging
-- schema even when invoked by a privileged operator without PGOPTIONS.
SET LOCAL search_path = staging, public;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_reasoning_effort.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(16) NOT NULL DEFAULT 'high';
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(16) NOT NULL DEFAULT 'high';
ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(16) NOT NULL DEFAULT 'high';
ALTER TABLE chat_openrouter_provider_calls
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(16) NOT NULL DEFAULT 'high';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_sessions'::regclass
          AND conname = 'chat_sessions_reasoning_effort_check'
    ) THEN
        ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_reasoning_effort_check
            CHECK (reasoning_effort IN ('low','high','max'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_messages'::regclass
          AND conname = 'chat_messages_reasoning_effort_check'
    ) THEN
        ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_reasoning_effort_check
            CHECK (reasoning_effort IN ('low','high','max'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_turn_capabilities'::regclass
          AND conname = 'chat_turn_capabilities_reasoning_effort_check'
    ) THEN
        ALTER TABLE chat_turn_capabilities
            ADD CONSTRAINT chat_turn_capabilities_reasoning_effort_check
            CHECK (reasoning_effort IN ('low','high','max'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_openrouter_provider_calls'::regclass
          AND conname = 'chat_openrouter_provider_calls_reasoning_effort_check'
    ) THEN
        ALTER TABLE chat_openrouter_provider_calls
            ADD CONSTRAINT chat_openrouter_provider_calls_reasoning_effort_check
            CHECK (reasoning_effort IN ('low','high','max'));
    END IF;
END $$;

GRANT SELECT, UPDATE (reasoning_effort) ON chat_sessions TO pwc_staging;
GRANT SELECT, UPDATE (reasoning_effort) ON chat_messages TO pwc_staging;
GRANT SELECT, UPDATE (reasoning_effort) ON chat_turn_capabilities TO pwc_staging;
GRANT SELECT, UPDATE (reasoning_effort)
    ON chat_openrouter_provider_calls TO pwc_staging;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        REVOKE UPDATE (reasoning_effort) ON chat_sessions FROM paperswithcode_user;
        REVOKE UPDATE (reasoning_effort) ON chat_messages FROM paperswithcode_user;
        REVOKE UPDATE (reasoning_effort) ON chat_turn_capabilities FROM paperswithcode_user;
        REVOKE UPDATE (reasoning_effort)
            ON chat_openrouter_provider_calls FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
