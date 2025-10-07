-- Setup script for Repository Star History table
-- This table tracks historical GitHub star counts over time to enable trending metrics

-- =============================================================================
-- TABLE CREATION: repository_star_history
-- =============================================================================

CREATE TABLE IF NOT EXISTS repository_star_history (
    id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    num_stars INTEGER NOT NULL,
    snapshot_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Prevent duplicate snapshots for the same repository at the same time
    UNIQUE(repository_id, snapshot_at)
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Index for querying history by repository
CREATE INDEX IF NOT EXISTS idx_star_history_repository_id
    ON repository_star_history(repository_id);

-- Index for querying by time
CREATE INDEX IF NOT EXISTS idx_star_history_snapshot_at
    ON repository_star_history(snapshot_at DESC);

-- Composite index for trending queries (recent snapshots for a repository)
CREATE INDEX IF NOT EXISTS idx_star_history_repo_time
    ON repository_star_history(repository_id, snapshot_at DESC);

-- Index for finding recent snapshots across all repos
CREATE INDEX IF NOT EXISTS idx_star_history_recent
    ON repository_star_history(snapshot_at DESC, repository_id);

-- =============================================================================
-- ADD num_stars_updated_at TO repositories TABLE (if not exists)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'repositories' AND column_name = 'num_stars_updated_at'
    ) THEN
        ALTER TABLE repositories ADD COLUMN num_stars_updated_at TIMESTAMP WITH TIME ZONE;
        CREATE INDEX IF NOT EXISTS idx_repositories_stars_updated_at
            ON repositories(num_stars_updated_at);
    END IF;
END $$;

-- =============================================================================
-- FUNCTION: Calculate Star Velocity (stars gained per hour)
-- =============================================================================

CREATE OR REPLACE FUNCTION calculate_star_velocity(
    p_repository_id BIGINT,
    p_hours_lookback INTEGER DEFAULT 24
) RETURNS NUMERIC AS $$
DECLARE
    v_recent_stars INTEGER;
    v_old_stars INTEGER;
    v_hours_elapsed NUMERIC;
    v_velocity NUMERIC;
BEGIN
    -- Get the most recent star count
    SELECT num_stars INTO v_recent_stars
    FROM repository_star_history
    WHERE repository_id = p_repository_id
    ORDER BY snapshot_at DESC
    LIMIT 1;

    -- Get star count from N hours ago
    SELECT num_stars INTO v_old_stars
    FROM repository_star_history
    WHERE repository_id = p_repository_id
    AND snapshot_at <= (NOW() - INTERVAL '1 hour' * p_hours_lookback)
    ORDER BY snapshot_at DESC
    LIMIT 1;

    -- If we don't have enough history, return NULL
    IF v_recent_stars IS NULL OR v_old_stars IS NULL THEN
        RETURN NULL;
    END IF;

    -- Calculate velocity (stars per hour)
    v_velocity := (v_recent_stars - v_old_stars)::NUMERIC / p_hours_lookback::NUMERIC;

    RETURN v_velocity;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- FUNCTION: Calculate Trending Score (weighted velocity with decay)
-- =============================================================================

CREATE OR REPLACE FUNCTION calculate_trending_score(
    p_repository_id BIGINT,
    p_hours_lookback INTEGER DEFAULT 24,
    p_recency_weight NUMERIC DEFAULT 2.0
) RETURNS NUMERIC AS $$
DECLARE
    v_velocity NUMERIC;
    v_current_stars INTEGER;
    v_hours_since_update NUMERIC;
    v_recency_factor NUMERIC;
    v_trending_score NUMERIC;
BEGIN
    -- Get velocity
    v_velocity := calculate_star_velocity(p_repository_id, p_hours_lookback);

    IF v_velocity IS NULL THEN
        RETURN NULL;
    END IF;

    -- Get current star count (for normalization)
    SELECT num_stars INTO v_current_stars
    FROM repositories
    WHERE id = p_repository_id;

    -- Calculate hours since last update
    SELECT EXTRACT(EPOCH FROM (NOW() - snapshot_at)) / 3600 INTO v_hours_since_update
    FROM repository_star_history
    WHERE repository_id = p_repository_id
    ORDER BY snapshot_at DESC
    LIMIT 1;

    -- Calculate recency factor (decay over time)
    -- Recent updates get higher weight
    v_recency_factor := EXP(-v_hours_since_update / p_hours_lookback * p_recency_weight);

    -- Trending score combines absolute velocity with recency
    -- Higher velocity + more recent = higher score
    v_trending_score := v_velocity * v_recency_factor * 100;

    RETURN v_trending_score;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- VIEW: Trending Repositories (last 24 hours)
-- =============================================================================

CREATE OR REPLACE VIEW trending_repositories_24h AS
SELECT
    r.id,
    r.url,
    r.owner,
    r.name,
    r.num_stars as current_stars,
    calculate_star_velocity(r.id, 24) as velocity_24h,
    calculate_trending_score(r.id, 24) as trending_score,
    (
        SELECT num_stars
        FROM repository_star_history
        WHERE repository_id = r.id
        AND snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY snapshot_at DESC
        LIMIT 1
    ) as stars_24h_ago,
    r.num_stars - (
        SELECT COALESCE(num_stars, r.num_stars)
        FROM repository_star_history
        WHERE repository_id = r.id
        AND snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY snapshot_at DESC
        LIMIT 1
    ) as stars_gained_24h
FROM repositories r
WHERE r.owner IS NOT NULL
AND r.name IS NOT NULL
AND EXISTS (
    SELECT 1 FROM repository_star_history
    WHERE repository_id = r.id
    AND snapshot_at >= (NOW() - INTERVAL '48 hours')
)
ORDER BY trending_score DESC NULLS LAST;

-- =============================================================================
-- VIEW: Trending Papers (based on their repositories)
-- =============================================================================

CREATE OR REPLACE VIEW trending_papers_24h AS
SELECT
    p.id as paper_id,
    p.arxiv_id,
    p.title,
    p.date_published,
    r.id as repository_id,
    r.url as repository_url,
    r.owner,
    r.name as repo_name,
    r.num_stars as current_stars,
    calculate_star_velocity(r.id, 24) as velocity_24h,
    calculate_trending_score(r.id, 24) as trending_score,
    r.num_stars - (
        SELECT COALESCE(num_stars, r.num_stars)
        FROM repository_star_history
        WHERE repository_id = r.id
        AND snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY snapshot_at DESC
        LIMIT 1
    ) as stars_gained_24h,
    -- Paper age in days
    EXTRACT(EPOCH FROM (NOW() - p.date_published)) / 86400 as paper_age_days
FROM papers p
JOIN paper_repositories pr ON p.id = pr.paper_id
JOIN repositories r ON pr.repository_id = r.id
WHERE r.owner IS NOT NULL
AND r.name IS NOT NULL
AND pr.is_official = TRUE  -- Only official repositories
AND p.date_published >= (NOW() - INTERVAL '6 months')  -- Recent papers only
AND EXISTS (
    SELECT 1 FROM repository_star_history
    WHERE repository_id = r.id
    AND snapshot_at >= (NOW() - INTERVAL '48 hours')
)
ORDER BY trending_score DESC NULLS LAST, current_stars DESC;

-- =============================================================================
-- TABLE DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE repository_star_history IS
'Historical snapshots of GitHub repository star counts for trending analysis';

COMMENT ON COLUMN repository_star_history.repository_id IS
'Foreign key reference to repositories table';

COMMENT ON COLUMN repository_star_history.num_stars IS
'Number of GitHub stars at the time of snapshot';

COMMENT ON COLUMN repository_star_history.snapshot_at IS
'Timestamp when this star count was recorded';

COMMENT ON FUNCTION calculate_star_velocity(BIGINT, INTEGER) IS
'Calculate the rate of star gain per hour over a specified lookback period';

COMMENT ON FUNCTION calculate_trending_score(BIGINT, INTEGER, NUMERIC) IS
'Calculate a trending score combining velocity and recency with exponential decay';

COMMENT ON VIEW trending_repositories_24h IS
'Repositories ranked by trending score (star velocity with recency weighting) over last 24 hours';

COMMENT ON VIEW trending_papers_24h IS
'Papers ranked by their repository trending scores (recent papers only, last 6 months)';

-- =============================================================================
-- EXAMPLE QUERIES
-- =============================================================================

-- Get top 10 trending repositories
-- SELECT * FROM trending_repositories_24h LIMIT 10;

-- Get top 10 trending papers
-- SELECT * FROM trending_papers_24h LIMIT 10;

-- Get star history for a specific repository
-- SELECT * FROM repository_star_history
-- WHERE repository_id = 123
-- ORDER BY snapshot_at DESC LIMIT 100;

-- Calculate velocity for a specific repo (last 24 hours)
-- SELECT calculate_star_velocity(123, 24);

-- Calculate trending score
-- SELECT calculate_trending_score(123, 24, 2.0);

-- =============================================================================
-- SCRIPT COMPLETION MESSAGE
-- =============================================================================

SELECT
    '✅ STAR HISTORY SETUP COMPLETE' as status,
    'Repository star history tracking is ready' as message,
    'Table, indexes, functions, and views created' as details;
