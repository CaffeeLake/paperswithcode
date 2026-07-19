-- Accelerate deterministic exact-title identity lookups in all paper-search modes.
-- Run outside a transaction because CONCURRENTLY cannot run inside one.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_papers_latest_normalized_title
ON papers (lower(regexp_replace(btrim(title), '\s+', ' ', 'g')))
WHERE is_latest_version;
