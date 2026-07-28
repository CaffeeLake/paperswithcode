BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_shares.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (
           SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner'
       ) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(64);

CREATE TABLE IF NOT EXISTS chat_shares (
    id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL UNIQUE
        REFERENCES chat_sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_share_messages (
    share_id UUID NOT NULL REFERENCES chat_shares(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    PRIMARY KEY (share_id, position),
    CONSTRAINT uq_chat_share_messages_message UNIQUE (share_id, message_id)
);

ALTER TABLE chat_shares OWNER TO pwc_staging_owner;
ALTER TABLE chat_share_messages OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_shares, chat_share_messages
    TO pwc_staging;
GRANT SELECT, UPDATE (finish_reason) ON chat_messages TO pwc_staging;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        REVOKE ALL ON chat_shares, chat_share_messages
            FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
