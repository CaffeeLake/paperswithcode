-- Migration: Reset poisoned repository trending scores
-- Date: 2026-06-25
-- Description: Clears decayed subnormal EMA values that can make the hourly
--              calculate_trending_scores cron fail with numeric underflow.

-- Keep NULL for never-calculated repositories. Existing tiny positive values
-- carry no useful ranking signal after NUMERIC(10, 4) rounding, so zero them.
UPDATE repositories
SET trending_score = 0,
    trending_score_updated_at = COALESCE(trending_score_updated_at, NOW()),
    updated_at = NOW()
WHERE trending_score IS NOT NULL
  AND (
      trending_score < 0.0001
      OR trending_score > 999999.9999
      OR trending_score::text = 'NaN'
  );
