-- Run after the bounded entity-vector backfill reports zero remaining rows.
-- CREATE INDEX CONCURRENTLY statements must execute outside a transaction.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_datasets_search_vector
ON datasets USING gin (search_vector);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_methods_search_vector
ON methods USING gin (search_vector);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_search_vector
ON tasks USING gin (search_vector);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_datasets_name_search_trgm
ON datasets USING gist (pwc_entity_search_normalize(name) gist_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_methods_name_search_trgm
ON methods USING gist (pwc_entity_search_normalize(name) gist_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_name_search_trgm
ON tasks USING gist (pwc_entity_search_normalize(name) gist_trgm_ops);
