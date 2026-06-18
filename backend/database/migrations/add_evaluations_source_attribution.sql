-- Migration: Add source attribution columns to evaluations
--
-- `paper_id` remains the evaluated paper/model attribution. `source_url` is
-- the canonical place where the score was found, and `external` marks whether
-- that source is independent of the evaluated paper/model's own linked
-- resources.
--
-- Created: 2026-06-18
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_evaluations_source_attribution.sql

BEGIN;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS source_url TEXT;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS external BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE evaluations
SET source_url = external_source_url
WHERE source_url IS NULL
  AND external_source_url IS NOT NULL;

UPDATE evaluations
SET external = FALSE
WHERE source_url IS NULL;

WITH eval_sources AS (
    SELECT
        e.id AS evaluation_id,
        lower(regexp_replace(trim(e.source_url), '/+$', '')) AS source_key,
        p.id AS paper_id,
        p.arxiv_id,
        lower(regexp_replace(trim(p.source_url), '/+$', '')) AS paper_source_key,
        ARRAY(
            SELECT lower(regexp_replace(trim(url), '/+$', ''))
            FROM unnest(COALESCE(p.hf_models, ARRAY[]::text[])) AS url
        ) AS hf_model_keys,
        ARRAY(
            SELECT lower(regexp_replace(trim(url), '/+$', ''))
            FROM unnest(COALESCE(p.hf_datasets, ARRAY[]::text[])) AS url
        ) AS hf_dataset_keys,
        ARRAY(
            SELECT lower(regexp_replace(trim(url), '/+$', ''))
            FROM unnest(COALESCE(p.hf_spaces, ARRAY[]::text[])) AS url
        ) AS hf_space_keys
    FROM evaluations e
    JOIN papers p ON p.id = e.paper_id
    WHERE e.source_url IS NOT NULL
),
related_sources AS (
    SELECT evaluation_id, 'paper:' || paper_id::text AS source_key FROM eval_sources
    UNION ALL
    SELECT evaluation_id, '/paper/' || paper_id::text FROM eval_sources
    UNION ALL
    SELECT evaluation_id, 'https://paperswithcode.co/paper/' || paper_id::text FROM eval_sources
    UNION ALL
    SELECT evaluation_id, paper_source_key FROM eval_sources WHERE paper_source_key IS NOT NULL
    UNION ALL
    SELECT evaluation_id, 'arxiv:' || lower(regexp_replace(arxiv_id, 'v[0-9]+$', '')) FROM eval_sources WHERE arxiv_id IS NOT NULL
    UNION ALL
    SELECT evaluation_id, 'https://arxiv.org/abs/' || lower(regexp_replace(arxiv_id, 'v[0-9]+$', '')) FROM eval_sources WHERE arxiv_id IS NOT NULL
    UNION ALL
    SELECT evaluation_id, 'https://arxiv.org/pdf/' || lower(regexp_replace(arxiv_id, 'v[0-9]+$', '')) || '.pdf' FROM eval_sources WHERE arxiv_id IS NOT NULL
    UNION ALL
    SELECT evaluation_id, '/paper/' || lower(regexp_replace(arxiv_id, 'v[0-9]+$', '')) FROM eval_sources WHERE arxiv_id IS NOT NULL
    UNION ALL
    SELECT evaluation_id, 'https://paperswithcode.co/paper/' || lower(regexp_replace(arxiv_id, 'v[0-9]+$', '')) FROM eval_sources WHERE arxiv_id IS NOT NULL
    UNION ALL
    SELECT evaluation_id, unnest(hf_model_keys) FROM eval_sources
    UNION ALL
    SELECT evaluation_id, unnest(hf_dataset_keys) FROM eval_sources
    UNION ALL
    SELECT evaluation_id, unnest(hf_space_keys) FROM eval_sources
    UNION ALL
    SELECT e.id, lower(regexp_replace(trim(r.url), '/+$', ''))
    FROM evaluations e
    JOIN paper_repositories pr ON pr.paper_id = e.paper_id
    JOIN repositories r ON r.id = pr.repository_id
    WHERE e.source_url IS NOT NULL
    UNION ALL
    SELECT e.id, lower(regexp_replace(trim(pp.url), '/+$', ''))
    FROM evaluations e
    JOIN paper_project_pages ppp ON ppp.paper_id = e.paper_id
    JOIN project_pages pp ON pp.id = ppp.project_page_id
    WHERE e.source_url IS NOT NULL
    UNION ALL
    SELECT e.id, lower(regexp_replace(trim(ha.url), '/+$', ''))
    FROM evaluations e
    JOIN paper_hf_artifacts pha ON pha.paper_id = e.paper_id
    JOIN hf_artifacts ha ON ha.id = pha.hf_artifact_id
    WHERE e.source_url IS NOT NULL
)
UPDATE evaluations e
SET external = NOT EXISTS (
    SELECT 1
    FROM related_sources rs
    WHERE rs.evaluation_id = e.id
      AND rs.source_key = lower(regexp_replace(trim(e.source_url), '/+$', ''))
)
WHERE e.source_url IS NOT NULL;

UPDATE evaluations e
SET source_url = 'https://paperswithcode.co/benchmark/open-asr-leaderboard',
    external_source_url = 'https://paperswithcode.co/benchmark/open-asr-leaderboard',
    external = TRUE
FROM tasks t, datasets d
WHERE e.task_id = t.id
  AND e.dataset_id = d.id
  AND t.slug = 'automatic-speech-recognition'
  AND (
      d.slug IN (
          'open-asr-leaderboard',
          'ami-ihm',
          'common-voice',
          'earnings-22',
          'gigaspeech',
          'librispeech-clean',
          'librispeech-other',
          'spgispeech',
          'tedlium',
          'voxpopuli'
      )
      OR e.methodology LIKE 'Open ASR Leaderboard%'
  );

CREATE INDEX IF NOT EXISTS idx_evaluations_external
    ON evaluations (external);

CREATE INDEX IF NOT EXISTS idx_evaluations_source_url
    ON evaluations (source_url);

COMMENT ON COLUMN evaluations.source_url IS
'Canonical URL or paper:<id> reference where the evaluation score was found.';

COMMENT ON COLUMN evaluations.external IS
'True when source_url is independent of the evaluated paper/model release context.';

COMMIT;
