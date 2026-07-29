BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS logo_sha256 VARCHAR(64);

UPDATE public.organizations
SET logo_sha256 = encode(digest(logo_data, 'sha256'), 'hex')
WHERE logo_data IS NOT NULL
  AND logo_sha256 IS DISTINCT FROM encode(digest(logo_data, 'sha256'), 'hex');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.organizations'::regclass
          AND conname = 'organizations_logo_sha256_check'
    ) THEN
        ALTER TABLE public.organizations
            ADD CONSTRAINT organizations_logo_sha256_check
            CHECK (
                logo_sha256 IS NULL
                OR logo_sha256 ~ '^[0-9a-f]{64}$'
            ) NOT VALID;
    END IF;
END
$$;

ALTER TABLE public.organizations
    VALIDATE CONSTRAINT organizations_logo_sha256_check;

COMMIT;
