BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_shares.sql must run with search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION 'production chat migration requires paperswithcode_user';
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(64);

CREATE TABLE IF NOT EXISTS chat_shares (
    id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL UNIQUE
        REFERENCES chat_sessions(id) ON DELETE CASCADE,
    snapshot_version SMALLINT NOT NULL DEFAULT 1,
    messages JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_shares_messages_array_check
        CHECK (jsonb_typeof(messages) = 'array')
);

ALTER TABLE chat_shares
    ADD COLUMN IF NOT EXISTS snapshot_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS messages JSONB;

DO $$
DECLARE
    legacy_manifests_exist BOOLEAN;
BEGIN
    IF to_regclass('chat_share_messages') IS NOT NULL THEN
        EXECUTE
            'SELECT EXISTS (SELECT 1 FROM chat_share_messages LIMIT 1)'
            INTO legacy_manifests_exist;
        IF legacy_manifests_exist THEN
            RAISE EXCEPTION
                'legacy chat share manifests exist; migrate them before applying this schema';
        END IF;
    END IF;
END $$;

DROP TABLE IF EXISTS chat_share_messages;

UPDATE chat_shares SET messages = '[]'::jsonb WHERE messages IS NULL;
ALTER TABLE chat_shares ALTER COLUMN messages SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'chat_shares'::regclass
          AND conname = 'chat_shares_messages_array_check'
    ) THEN
        ALTER TABLE chat_shares
            ADD CONSTRAINT chat_shares_messages_array_check
            CHECK (jsonb_typeof(messages) = 'array');
    END IF;
END $$;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_shares OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_shares TO pwc_staging;
        GRANT SELECT, UPDATE (finish_reason) ON chat_messages TO pwc_staging;
        REVOKE ALL ON chat_shares FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_shares OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_shares TO paperswithcode_user;
        GRANT SELECT, UPDATE (finish_reason) ON chat_messages TO paperswithcode_user;
        REVOKE ALL ON chat_shares FROM pwc_staging;
    END IF;
END $$;

COMMIT;
