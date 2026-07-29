BEGIN;

-- Latent reasoning is a method family rather than a technique with one
-- introducing paper. Keep the automatic vocabulary deliberately narrow and
-- use exclusions for papers where the phrase means a dormant capability,
-- an ordinary latent variable, or an unrelated named stage.
INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'latent-reasoning',
    'Latent Reasoning',
    'Latent Reasoning',
    'Latent reasoning performs intermediate inference in continuous hidden states, recurrent activations, learned latent tokens, or other compact internal representations instead of verbalizing every step as natural-language chain-of-thought. These approaches can reduce decoding cost, preserve higher-bandwidth information, and support iterative or parallel computation before a final answer is emitted.',
    'latent reasoning',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2024,
    NULL,
    'https://x.com/TamazGadaev/status/2082198155287011402',
    'Latent reasoning reading path by Tamaz Gadaev',
    NULL,
    NULL,
    '[Training Large Language Models to Reason in a Continuous Latent Space](/paper/2412.06769)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

-- False positives found by reviewing every current title/abstract containing
-- the exact phrase "latent reasoning".
INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT
    p.id,
    m.id,
    'Phrase does not denote non-verbal intermediate reasoning'
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'latent-reasoning'
  AND p.is_latest_version
  AND p.arxiv_id IN (
      '2312.04684', -- latent variable over textual rationale skills
      '2409.03752', -- label for one stage in an attention-head taxonomy
      '2410.05262', -- unsupported hypothesis about a benchmarked model
      '2411.04282', -- latent distribution over sampled textual reasoning
      '2502.12744', -- low-probability textual paths described as latent ability
      '2506.13056', -- dormant reasoning capacity, not latent inference
      '2507.08567', -- explicitly distinguishes itself from latent reasoners
      '2509.04475', -- latent means untapped model potential
      '2509.23250', -- latent means untapped model ability
      '2510.09312', -- computational graphs of explicit textual CoT
      '2601.03717', -- student distribution over textual reasoning
      '2602.04856', -- internal analysis of explicit reasoning traces
      '2602.07125', -- latent means an implicit retrieval requirement
      '2602.16720', -- latent means untapped model potential
      '2602.21228', -- latent means an implicit instruction structure
      '2602.23720', -- phrase is used without a concrete latent mechanism
      '2603.14382', -- latent means dormant segmentation ability
      '2604.16913', -- visible System-2 monologues are called latent
      '2604.25444', -- latent means untapped model ability
      '2607.17674'  -- latent variable indexes textual response strategies
  )
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

-- If this migration is reapplied after an automatic keyword pass, exclusions
-- remain authoritative.
DELETE FROM paper_methods pm
USING paper_method_exclusions e, methods m
WHERE m.slug = 'latent-reasoning'
  AND pm.method_id = m.id
  AND e.method_id = m.id
  AND e.paper_id = pm.paper_id;

-- The five papers explicitly requested from the reading path. Three use
-- adjacent vocabulary ("continuous thought", "latent thought", or "latent
-- communication") and therefore would not be reached by the narrow keyword.
WITH requested_papers AS (
    SELECT p.id AS paper_id, m.id AS method_id
    FROM papers p
    CROSS JOIN methods m
    WHERE m.slug = 'latent-reasoning'
      AND p.is_latest_version
      AND p.arxiv_id IN (
          '2412.06769',
          '2505.12514',
          '2509.25239',
          '2604.22709',
          '2606.05711'
      )
),
inserted AS (
    INSERT INTO paper_methods (paper_id, method_id)
    SELECT paper_id, method_id
    FROM requested_papers
    ON CONFLICT (paper_id, method_id) DO NOTHING
    RETURNING paper_id, method_id
)
INSERT INTO paper_method_evidence (
    paper_id,
    method_id,
    evidence_type,
    details
)
SELECT
    paper_id,
    method_id,
    'manual',
    '{"source":"https://x.com/TamazGadaev/status/2082198155287011402"}'::jsonb
FROM requested_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now(),
    details = EXCLUDED.details;

-- Conservatively backfill the exact lowercase keyword with the same word
-- boundaries used by backend.utils.keyword_matching.
WITH keyword_papers AS (
    SELECT p.id AS paper_id, m.id AS method_id
    FROM papers p
    CROSS JOIN methods m
    WHERE m.slug = 'latent-reasoning'
      AND p.is_latest_version
      AND lower(concat_ws(' ', p.title, p.abstract))
          ~ '(^|[^a-z0-9_])latent reasoning(s)?([^a-z0-9_]|$)'
      AND NOT EXISTS (
          SELECT 1
          FROM paper_method_exclusions e
          WHERE e.paper_id = p.id
            AND e.method_id = m.id
      )
),
inserted AS (
    INSERT INTO paper_methods (paper_id, method_id)
    SELECT paper_id, method_id
    FROM keyword_papers
    ON CONFLICT (paper_id, method_id) DO NOTHING
    RETURNING paper_id, method_id
)
INSERT INTO paper_method_evidence (
    paper_id,
    method_id,
    evidence_type
)
SELECT paper_id, method_id, 'keyword'
FROM keyword_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

COMMIT;
