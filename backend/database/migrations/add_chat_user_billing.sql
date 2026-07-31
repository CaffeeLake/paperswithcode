BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_user_billing.sql must run with search_path staging,public';
    END IF;
END $$;

ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS provider_token_encrypted TEXT;

COMMIT;
