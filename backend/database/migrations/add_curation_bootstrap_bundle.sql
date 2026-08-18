BEGIN;

ALTER TABLE paper_curation_jobs
    ADD COLUMN IF NOT EXISTS bootstrap_bundle JSONB;

COMMENT ON COLUMN paper_curation_jobs.bootstrap_bundle IS
    'Hash-validated allowlisted remote worker bootstrap snapshot bound before dispatch';

COMMIT;
