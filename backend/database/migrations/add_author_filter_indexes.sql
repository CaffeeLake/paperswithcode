-- Run outside a transaction because CONCURRENTLY cannot run inside one.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_authors_normalized_name
    ON authors ((lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))));

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_authors_lower_hf_username
    ON authors ((lower(hf_username)))
    WHERE hf_username IS NOT NULL;
