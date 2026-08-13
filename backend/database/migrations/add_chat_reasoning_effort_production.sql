BEGIN;

-- Keep this provider-independent migration confined to the common production
-- chat schema in public.
SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_reasoning_effort_production.sql must run in public';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        RAISE EXCEPTION
            'paperswithcode_user must exist before this migration';
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

ALTER TABLE chat_sessions OWNER TO paperswithcode_user;
ALTER TABLE chat_messages OWNER TO paperswithcode_user;
ALTER TABLE chat_turn_capabilities OWNER TO paperswithcode_user;
ALTER TABLE chat_openrouter_provider_calls OWNER TO paperswithcode_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    chat_sessions, chat_messages, chat_turn_capabilities,
    chat_openrouter_provider_calls
TO paperswithcode_user;
REVOKE ALL ON
    chat_sessions, chat_messages, chat_turn_capabilities,
    chat_openrouter_provider_calls
FROM pwc_staging;

COMMIT;
