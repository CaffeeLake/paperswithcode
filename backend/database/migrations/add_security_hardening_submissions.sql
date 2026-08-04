BEGIN;

DO $$
BEGIN
  IF current_schema() NOT IN ('public', 'staging') THEN
    RAISE EXCEPTION
      'security hardening migration must run with public or staging first in search_path (got %)',
      current_schema();
  END IF;
  IF current_schema() = 'staging' AND (
    NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') OR
    NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')
  ) THEN
    RAISE EXCEPTION 'pwc_staging and pwc_staging_owner roles must exist';
  END IF;
END
$$;

ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS hf_subject VARCHAR(255);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS source_ip VARCHAR(64);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS applied_payload JSONB;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS result_entity_type VARCHAR(64);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS result_entity_id VARCHAR(255);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS catalog_event_id UUID REFERENCES catalog_mutation_events(id) ON DELETE RESTRICT;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS conflict_payload JSONB;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS reviewed_by_kind VARCHAR(16);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS reviewed_by_hf_subject VARCHAR(255);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS review_run_id UUID;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS review_model VARCHAR(255);
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS review_evidence JSONB;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE pending_paper_edits ADD COLUMN IF NOT EXISTS user_review_reason TEXT;

ALTER TABLE pending_paper_edits DROP CONSTRAINT IF EXISTS pending_paper_edits_edit_type_check;
ALTER TABLE pending_paper_edits ADD CONSTRAINT pending_paper_edits_edit_type_check CHECK (
  edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages',
    'source_url', 'hf_artifacts', 'organizations', 'new_task', 'new_method',
    'new_benchmark', 'new_metric', 'new_conference', 'new_external_paper')
);
ALTER TABLE pending_paper_edits DROP CONSTRAINT IF EXISTS pending_paper_edits_reviewed_by_kind_check;
ALTER TABLE pending_paper_edits ADD CONSTRAINT pending_paper_edits_reviewed_by_kind_check
  CHECK (reviewed_by_kind IS NULL OR reviewed_by_kind IN ('human', 'codex'));

CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_hf_subject
  ON pending_paper_edits (hf_subject, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pending_paper_edits_source_ip
  ON pending_paper_edits (source_ip, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_paper_edits_subject_idempotency
  ON pending_paper_edits (hf_subject, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_profiles (
  hf_subject VARCHAR(255) PRIMARY KEY,
  current_username VARCHAR(255) NOT NULL UNIQUE,
  is_submission_suspended BOOLEAN NOT NULL DEFAULT FALSE,
  suspension_reason TEXT,
  suspended_at TIMESTAMPTZ,
  suspended_by_hf_subject VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS user_profile_aliases (
  alias VARCHAR(255) PRIMARY KEY,
  hf_subject VARCHAR(255) NOT NULL REFERENCES user_profiles(hf_subject) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_profile_aliases_subject
  ON user_profile_aliases (hf_subject);

DO $$
DECLARE
  pending_owner NAME;
BEGIN
  SELECT tableowner INTO pending_owner
  FROM pg_tables
  WHERE schemaname = current_schema() AND tablename = 'pending_paper_edits';

  IF pending_owner IS NULL THEN
    RAISE EXCEPTION 'pending_paper_edits is missing from schema %', current_schema();
  END IF;

  EXECUTE format('ALTER TABLE %I.user_profiles OWNER TO %I', current_schema(), pending_owner);
  EXECUTE format('ALTER TABLE %I.user_profile_aliases OWNER TO %I', current_schema(), pending_owner);

  IF current_schema() = 'staging' THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON user_profiles, user_profile_aliases TO pwc_staging;
  END IF;
END
$$;

COMMIT;
