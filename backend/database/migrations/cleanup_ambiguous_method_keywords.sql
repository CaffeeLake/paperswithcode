-- Remove ambiguous method keywords and links supported only by those matches.
--
-- Uppercase keywords use substring matching, so the bare FC and ACT acronyms
-- matched unrelated strings such as functional connectivity, FCN, NACT, and
-- LACT. "discriminator" is not specific to GANs, and CNN/DailyMail mentions do
-- not establish that a paper uses convolution.

BEGIN;

UPDATE methods
SET keywords = 'Fast Conformer, FastConformer, fast conformer, fast-conformer',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'fast-conformer';

UPDATE methods
SET keywords = 'Action Chunking with Transformers, action chunking transformer, action chunking',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'act';

UPDATE methods
SET keywords = 'GAN, generative adversarial network',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gan';

-- CNN remains a useful Convolution keyword, so retain durable paper-specific
-- exclusions for papers whose only CNN mention is the CNN/DailyMail dataset.
INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT pm.paper_id,
       pm.method_id,
       'CNN refers only to the CNN/DailyMail dataset, not the Convolution method'
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id
JOIN papers p ON p.id = pm.paper_id
WHERE m.slug = 'convolution'
  AND (
      COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
  ) ~* '\mcnn[ /-]*dailymail\M'
  AND REGEXP_REPLACE(
      COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, ''),
      'cnn[ /-]*dailymail',
      '',
      'gi'
  ) !~* '\mcnn\M|convolution'
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Delete unsupported parent links first so their keyword and legacy_unknown
-- evidence is removed by the parent foreign key's ON DELETE CASCADE. Preserve
-- any link backed by source, reference, or manual evidence.
WITH candidates AS (
    SELECT pm.paper_id, pm.method_id
    FROM paper_methods pm
    JOIN methods m ON m.id = pm.method_id
    JOIN papers p ON p.id = pm.paper_id
    WHERE EXISTS (
        SELECT 1
        FROM paper_method_evidence keyword_evidence
        WHERE keyword_evidence.paper_id = pm.paper_id
          AND keyword_evidence.method_id = pm.method_id
          AND keyword_evidence.evidence_type = 'keyword'
    )
      AND NOT EXISTS (
        SELECT 1
        FROM paper_method_evidence independent_evidence
        WHERE independent_evidence.paper_id = pm.paper_id
          AND independent_evidence.method_id = pm.method_id
          AND independent_evidence.evidence_type IN ('source', 'reference', 'manual')
    )
      AND (
          (
              m.slug = 'fast-conformer'
              AND (
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
              ) !~* 'fast[ -]?conformer'
          )
          OR (
              m.slug = 'act'
              AND (
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
              ) !~* 'action[ -]chunking'
          )
          OR (
              m.slug = 'gan'
              AND STRPOS(
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, ''),
                  'GAN'
              ) = 0
              AND (
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
              ) !~* 'generative[ -]adversarial network'
          )
          OR (
              m.slug = 'convolution'
              AND (
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
              ) ~* '\mcnn[ /-]*dailymail\M'
              AND REGEXP_REPLACE(
                  COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, ''),
                  'cnn[ /-]*dailymail',
                  '',
                  'gi'
              ) !~* '\mcnn\M|convolution'
          )
      )
)
DELETE FROM paper_methods pm
USING candidates
WHERE pm.paper_id = candidates.paper_id
  AND pm.method_id = candidates.method_id;

-- If a future database has independent evidence for one of these associations,
-- retain the parent link but remove the ambiguous keyword evidence.
DELETE FROM paper_method_evidence evidence
USING methods m, papers p
WHERE evidence.method_id = m.id
  AND evidence.paper_id = p.id
  AND evidence.evidence_type = 'keyword'
  AND (
      (
          m.slug = 'fast-conformer'
          AND (
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
          ) !~* 'fast[ -]?conformer'
      )
      OR (
          m.slug = 'act'
          AND (
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
          ) !~* 'action[ -]chunking'
      )
      OR (
          m.slug = 'gan'
          AND STRPOS(
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, ''),
              'GAN'
          ) = 0
          AND (
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
          ) !~* 'generative[ -]adversarial network'
      )
      OR (
          m.slug = 'convolution'
          AND (
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, '')
          ) ~* '\mcnn[ /-]*dailymail\M'
          AND REGEXP_REPLACE(
              COALESCE(p.title, '') || ' ' || COALESCE(p.abstract, ''),
              'cnn[ /-]*dailymail',
              '',
              'gi'
          ) !~* '\mcnn\M|convolution'
      )
  );

COMMIT;
