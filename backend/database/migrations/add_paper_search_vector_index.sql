-- Run after the bounded backfill reports zero remaining rows.
-- CREATE INDEX CONCURRENTLY must be executed outside a transaction; psql does
-- that for this single-statement file. IF NOT EXISTS makes retries safe.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_latest_search_vector
ON papers USING gin (search_vector)
WHERE is_latest_version;
