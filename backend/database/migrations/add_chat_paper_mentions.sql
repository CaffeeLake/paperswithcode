BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_paper_mentions.sql must run with search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        RAISE EXCEPTION 'pwc_staging role must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS paper_mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS effective_prompt TEXT,
    ADD COLUMN IF NOT EXISTS langfuse_trace_id VARCHAR(64);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_messages'::regclass
          AND conname = 'chat_messages_paper_mentions_array_check'
    ) THEN
        ALTER TABLE chat_messages
            ADD CONSTRAINT chat_messages_paper_mentions_array_check
            CHECK (jsonb_typeof(paper_mentions) = 'array');
    END IF;
END $$;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        GRANT SELECT, UPDATE (paper_mentions, effective_prompt, langfuse_trace_id)
            ON chat_messages TO pwc_staging;
    ELSE
        GRANT SELECT, UPDATE (paper_mentions, effective_prompt, langfuse_trace_id)
            ON chat_messages TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
