-- Fuzzy and incomplete paper-title lookup for search query enrichment.
-- Run enable_pg_trgm.sql first and execute this file outside a transaction.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_latest_title_trgm
ON papers USING gist (lower(title) gist_trgm_ops)
WHERE is_latest_version;
