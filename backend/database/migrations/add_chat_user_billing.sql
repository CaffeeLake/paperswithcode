BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_user_billing.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS provider_token_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS provider_mode VARCHAR(32),
    ADD COLUMN IF NOT EXISTS provider_credential_revision UUID,
    ADD COLUMN IF NOT EXISTS provider_error_code VARCHAR(64);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_turn_capabilities'::regclass
          AND conname = 'chat_turn_capabilities_provider_mode_check'
    ) THEN
        ALTER TABLE chat_turn_capabilities
            ADD CONSTRAINT chat_turn_capabilities_provider_mode_check CHECK (
                provider_mode IS NULL OR provider_mode IN
                ('huggingface','openrouter_funded','openrouter_byok')
            );
    END IF;
END $$;

COMMIT;
