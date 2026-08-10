BEGIN;

DO $$
BEGIN
  IF current_schema() <> 'staging' THEN
    RAISE EXCEPTION
      'staging access request migration requires search_path=staging,public (got %)',
      current_schema();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') OR
     NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
    RAISE EXCEPTION 'pwc_staging and pwc_staging_owner roles must exist';
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS staging_access_requests (
  hf_subject VARCHAR(255) PRIMARY KEY,
  hf_username VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staging_access_requests_status_created
  ON staging_access_requests (status, created_at);

ALTER TABLE staging_access_requests OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE ON staging_access_requests TO pwc_staging;

COMMENT ON TABLE staging_access_requests IS
'Contributor access requests from Hugging Face identities verified by the staging session cookie.';

COMMIT;
