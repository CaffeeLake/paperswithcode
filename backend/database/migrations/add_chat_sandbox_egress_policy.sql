BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_sandbox_egress_policy.sql requires search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_sandbox_leases
    ADD COLUMN IF NOT EXISTS egress_policy_digest VARCHAR(64) NOT NULL
        DEFAULT '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945';
ALTER TABLE chat_sandbox_pool
    ADD COLUMN IF NOT EXISTS egress_policy_digest VARCHAR(64) NOT NULL
        DEFAULT '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945';

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_sandbox_leases OWNER TO pwc_staging_owner;
        ALTER TABLE chat_sandbox_pool OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_leases TO pwc_staging;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO pwc_staging;
        REVOKE ALL ON chat_sandbox_leases FROM paperswithcode_user;
        REVOKE ALL ON chat_sandbox_pool FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_sandbox_leases OWNER TO paperswithcode_user;
        ALTER TABLE chat_sandbox_pool OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_leases TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_pool TO paperswithcode_user;
        REVOKE ALL ON chat_sandbox_leases FROM pwc_staging;
        REVOKE ALL ON chat_sandbox_pool FROM pwc_staging;
    END IF;
END $$;

COMMIT;
