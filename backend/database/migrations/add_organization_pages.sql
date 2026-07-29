-- Organization discovery, Hugging Face synchronization, logo cache, and
-- rolling-trending state. Idempotent and safe to re-run.

BEGIN;

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS hf_slug VARCHAR(100);
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS display_order INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS last_hf_synced_at TIMESTAMPTZ;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS logo_data BYTEA;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS logo_mime_type VARCHAR(50);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS hf_paper_count INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS trending_score DOUBLE PRECISION;
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS trending_score_updated_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_hf_slug
    ON organizations(hf_slug) WHERE hf_slug IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_organizations_featured_trending
    ON organizations(is_featured, trending_score DESC);
CREATE INDEX IF NOT EXISTS idx_organizations_featured_order
    ON organizations(is_featured, display_order);

CREATE TABLE IF NOT EXISTS organization_trending_history (
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    raw_score DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_organization_trending_history_date
    ON organization_trending_history(snapshot_date);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE organization_trending_history TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE organization_trending_history IS
'Daily raw paper-momentum totals used for rolling 30-day organization ranks.';

DROP TRIGGER IF EXISTS update_organization_trending_history_updated_at
    ON organization_trending_history;
CREATE TRIGGER update_organization_trending_history_updated_at
    BEFORE UPDATE ON organization_trending_history
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
