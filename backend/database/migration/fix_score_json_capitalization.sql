-- Migration: Fix capitalization in metrics JSON field
-- Updates evaluations that have "Score" in their metrics JSON to use lowercase "score"
--
-- Created: November 2025
-- Usage: psql -U paperswithcode_user -h localhost -d paperswithcode_hf -f backend/database/migration/fix_score_json_capitalization.sql

BEGIN;

-- Update evaluations with "Score" in JSON to use "score"
UPDATE evaluations
SET metrics = jsonb_set(
    (metrics - 'Score')::jsonb,
    '{score}',
    metrics->'Score'
)
WHERE metrics::text LIKE '%"Score"%';

-- Verification
SELECT
    'Evaluations with Score in JSON (should be 0)' AS check_type,
    COUNT(*) AS count
FROM evaluations
WHERE metrics::text LIKE '%"Score"%';

SELECT
    'Sample evaluations with lowercase score' AS check_type,
    COUNT(*) AS count
FROM evaluations
WHERE best_metric = 'score'
LIMIT 1;

COMMIT;
