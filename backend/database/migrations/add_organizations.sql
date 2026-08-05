-- Migration: Add organizations table and paper_organizations junction
--
-- Normalizes organization metadata (NVIDIA, Google, Meta, etc.) sourced
-- primarily from Hugging Face org profiles, and links papers to the
-- lab/company behind them via paper_organizations.
--
-- Created: 2026-06-04
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_organizations.sql

BEGIN;

CREATE TABLE IF NOT EXISTS organizations (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    hf_url VARCHAR(500),
    logo_url VARCHAR(1000),
    website_url VARCHAR(500),
    github_url VARCHAR(500),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);

CREATE TABLE IF NOT EXISTS paper_organizations (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    added_by_hf_subject VARCHAR(255),
    added_by_hf_username VARCHAR(255),
    PRIMARY KEY (paper_id, organization_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_organizations_organization_id
    ON paper_organizations(organization_id);
CREATE INDEX IF NOT EXISTS idx_paper_organizations_paper_id
    ON paper_organizations(paper_id);

COMMENT ON TABLE organizations IS
'Normalized organization metadata (NVIDIA, Google, Meta, etc.).';

COMMENT ON TABLE paper_organizations IS
'Junction linking papers to organizations. source is manual or an importer tag.';

-- updated_at trigger (reuse existing function)
DROP TRIGGER IF EXISTS update_organizations_updated_at ON organizations;
CREATE TRIGGER update_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
