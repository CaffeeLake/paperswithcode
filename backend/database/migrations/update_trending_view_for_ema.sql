-- Migration: Update trending views to use EMA-based trending scores
-- Date: 2025-10-08
-- Description: Updates trending_papers_24h and trending_repositories_24h views to use
--              the new EMA-based trending_score from the repositories table instead of
--              calculating it on-the-fly

-- =============================================================================
-- VIEW: Trending Repositories (using EMA trending score)
-- =============================================================================

DROP VIEW IF EXISTS trending_repositories_24h CASCADE;

CREATE VIEW trending_repositories_24h AS
SELECT
    r.id,
    r.url,
    r.owner,
    r.name,
    r.num_stars as current_stars,
    -- Still calculate 24h velocity for display purposes (if we have history)
    (
        SELECT (r.num_stars - rsh.num_stars)::NUMERIC /
               GREATEST(EXTRACT(EPOCH FROM (NOW() - rsh.snapshot_at)) / 3600, 0.5)
        FROM repository_star_history rsh
        WHERE rsh.repository_id = r.id
        AND rsh.snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY rsh.snapshot_at DESC
        LIMIT 1
    ) as velocity_24h,
    -- Use the EMA-based trending score from the repositories table
    r.trending_score,
    -- Calculate stars gained in last 24 hours
    r.num_stars - (
        SELECT COALESCE(num_stars, r.num_stars)
        FROM repository_star_history
        WHERE repository_id = r.id
        AND snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY snapshot_at DESC
        LIMIT 1
    ) as stars_gained_24h,
    (
        SELECT num_stars
        FROM repository_star_history
        WHERE repository_id = r.id
        AND snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY snapshot_at DESC
        LIMIT 1
    ) as stars_24h_ago
FROM repositories r
WHERE r.owner IS NOT NULL
AND r.name IS NOT NULL
-- Only include repos with trending scores (indicates they have history)
AND r.trending_score IS NOT NULL
-- Only include repos updated recently (within last 24 hours)
AND r.trending_score_updated_at >= (NOW() - INTERVAL '24 hours')
ORDER BY r.trending_score DESC NULLS LAST, r.num_stars DESC;

COMMENT ON VIEW trending_repositories_24h IS
'Repositories ranked by EMA-based trending score (updated hourly by cron job)';


-- =============================================================================
-- VIEW: Trending Papers (based on EMA repository trending scores)
-- =============================================================================

DROP VIEW IF EXISTS trending_papers_24h CASCADE;

CREATE VIEW trending_papers_24h AS
SELECT
    p.id as paper_id,
    p.arxiv_id,
    p.title,
    p.abstract,
    p.date_published,
    r.id as repository_id,
    r.url as repository_url,
    r.owner,
    r.name as repo_name,
    r.num_stars as current_stars,
    -- Calculate 24h velocity for display
    (
        SELECT (r.num_stars - rsh.num_stars)::NUMERIC /
               GREATEST(EXTRACT(EPOCH FROM (NOW() - rsh.snapshot_at)) / 3600, 0.5)
        FROM repository_star_history rsh
        WHERE rsh.repository_id = r.id
        AND rsh.snapshot_at <= (NOW() - INTERVAL '24 hours')
        ORDER BY rsh.snapshot_at DESC
        LIMIT 1
    ) as velocity_24h,
    -- Use the EMA-based trending score
    r.trending_score,
    -- Calculate stars gained in last 24 hours
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
AND p.is_latest_version = TRUE  -- Only latest versions of papers
AND p.date_published >= (NOW() - INTERVAL '6 months')  -- Recent papers only (last 6 months)
-- Only include repos with trending scores
AND r.trending_score IS NOT NULL
-- Only include repos with recent trending score updates (within last 24 hours)
AND r.trending_score_updated_at >= (NOW() - INTERVAL '24 hours')
ORDER BY r.trending_score DESC NULLS LAST, r.num_stars DESC;

COMMENT ON VIEW trending_papers_24h IS
'Papers ranked by their repository EMA-based trending scores (recent papers only, updated hourly)';


-- =============================================================================
-- VERIFICATION
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ Trending views updated to use EMA-based trending scores';
    RAISE NOTICE '   - trending_repositories_24h: Uses repositories.trending_score';
    RAISE NOTICE '   - trending_papers_24h: Uses repositories.trending_score';
    RAISE NOTICE '';
    RAISE NOTICE '📊 Sample query to test:';
    RAISE NOTICE '   SELECT * FROM trending_papers_24h LIMIT 10;';
END $$;
