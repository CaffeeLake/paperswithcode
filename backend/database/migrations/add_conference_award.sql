-- Add optional award label to paper_conferences (e.g. outstanding, honorable_mention).
--
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_conference_award.sql

BEGIN;

ALTER TABLE paper_conferences
    ADD COLUMN IF NOT EXISTS award VARCHAR(50);

COMMENT ON COLUMN paper_conferences.award IS
'Optional conference award tier for this paper (e.g. outstanding, honorable_mention).';

CREATE INDEX IF NOT EXISTS idx_paper_conferences_award
    ON paper_conferences(conference_id, award)
    WHERE award IS NOT NULL;

COMMIT;
