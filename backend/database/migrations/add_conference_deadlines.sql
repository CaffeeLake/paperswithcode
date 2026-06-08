-- Migration: Add conference deadline metadata and conference_deadlines table
--
-- Extends the existing conferences table with deadline-feature metadata
-- (ERA tier, AI-domain tags, discrete city/country) and adds a child
-- conference_deadlines table holding submission/abstract/rebuttal deadlines
-- for the /ai-deadlines page.
--
-- Created: 2026-06-08
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_conference_deadlines.sql

BEGIN;

ALTER TABLE conferences
    ADD COLUMN IF NOT EXISTS tier VARCHAR(1),
    ADD COLUMN IF NOT EXISTS tags TEXT[],
    ADD COLUMN IF NOT EXISTS country VARCHAR(120),
    ADD COLUMN IF NOT EXISTS city VARCHAR(120);

COMMENT ON COLUMN conferences.tier IS
'ERA conference ranking (a/b/c); a indicates a top-tier venue.';
COMMENT ON COLUMN conferences.tags IS
'Free-form AI-domain tags (e.g. machine-learning, computer-vision).';

CREATE TABLE IF NOT EXISTS conference_deadlines (
    id BIGSERIAL PRIMARY KEY,
    conference_id BIGINT NOT NULL REFERENCES conferences(id) ON DELETE CASCADE,
    deadline_type VARCHAR(40),
    label VARCHAR(200),
    deadline_at TIMESTAMPTZ NOT NULL,
    timezone VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conference_deadlines_conference_id
    ON conference_deadlines(conference_id);
CREATE INDEX IF NOT EXISTS idx_conference_deadlines_deadline_at
    ON conference_deadlines(deadline_at);

COMMENT ON TABLE conference_deadlines IS
'Submission/abstract/rebuttal deadlines for a conference instance. '
'deadline_at is the absolute UTC instant; timezone preserves the original '
'source string (e.g. AoE, UTC-8, Asia/Seoul) for display.';

-- updated_at trigger (reuse existing function)
DROP TRIGGER IF EXISTS update_conference_deadlines_updated_at ON conference_deadlines;
CREATE TRIGGER update_conference_deadlines_updated_at
    BEFORE UPDATE ON conference_deadlines
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
