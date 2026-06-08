-- Migration: Add conferences table and paper_conferences junction
--
-- Normalizes conference metadata (name, slug, dates, venue, URL) and links
-- papers to conferences via paper_conferences.
--
-- Created: 2026-05-30
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_conferences.sql

BEGIN;

CREATE TABLE IF NOT EXISTS conferences (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    short_name VARCHAR(50),
    year INTEGER,
    url VARCHAR(500),
    start_date DATE,
    end_date DATE,
    venue VARCHAR(300),
    location VARCHAR(300),
    description TEXT,
    image_url VARCHAR(1000),
    image_credit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conferences_slug ON conferences(slug);
CREATE INDEX IF NOT EXISTS idx_conferences_year ON conferences(year DESC);

CREATE TABLE IF NOT EXISTS paper_conferences (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    conference_id BIGINT NOT NULL REFERENCES conferences(id) ON DELETE CASCADE,
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    PRIMARY KEY (paper_id, conference_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_conferences_conference_id
    ON paper_conferences(conference_id);
CREATE INDEX IF NOT EXISTS idx_paper_conferences_paper_id
    ON paper_conferences(paper_id);

COMMENT ON TABLE conferences IS
'Normalized conference metadata (CVPR, ICCV, NeurIPS, etc.).';

COMMENT ON TABLE paper_conferences IS
'Junction linking papers to conferences. source is manual or auto.';

-- updated_at trigger (reuse existing function)
DROP TRIGGER IF EXISTS update_conferences_updated_at ON conferences;
CREATE TRIGGER update_conferences_updated_at
    BEFORE UPDATE ON conferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
