BEGIN;

DO $$
BEGIN
  IF current_schema() <> 'staging' THEN
    RAISE EXCEPTION
      'staging access request email migration requires search_path=staging,public (got %)',
      current_schema();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') OR
     NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
    RAISE EXCEPTION 'pwc_staging and pwc_staging_owner roles must exist';
  END IF;
END
$$;

ALTER TABLE staging_access_requests
  ADD COLUMN IF NOT EXISTS email VARCHAR(320),
  ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'staging_access_requests_verified_email_check'
      AND conrelid = 'staging_access_requests'::regclass
  ) THEN
    ALTER TABLE staging_access_requests
      ADD CONSTRAINT staging_access_requests_verified_email_check
      CHECK (email IS NULL OR email_verified);
  END IF;
END
$$;

ALTER TABLE staging_access_requests OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE ON staging_access_requests TO pwc_staging;

COMMENT ON COLUMN staging_access_requests.email IS
'Verified Hugging Face email collected with explicit OAuth email scope for contributor access review.';
COMMENT ON COLUMN staging_access_requests.email_verified IS
'True only when Hugging Face userinfo returned email_verified=true.';

COMMIT;
