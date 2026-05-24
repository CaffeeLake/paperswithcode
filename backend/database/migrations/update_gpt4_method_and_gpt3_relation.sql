-- Migration: Link GPT-4 method and GPT paper lineage
--
-- Makes the GPT-4 Technical Report the canonical source for the GPT-4 method
-- and records GPT-4 as a follow-up to the GPT-3 paper.

BEGIN;

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
    'gpt-4',
    'GPT-4',
    'GPT-4',
    'GPT-4 is OpenAI''s multimodal large language model described in the [GPT-4 Technical Report](/paper/2303.08774). It extends the GPT family with stronger reasoning, coding, and academic benchmark performance, and accepts image and text inputs while producing text outputs.',
    'GPT-4, GPT4, Generative Pre-trained Transformer 4',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2303.08774'
          AND is_latest_version
        ORDER BY id DESC
        LIMIT 1
    ),
    NULL,
    'GPT-4 Technical Report',
    NULL,
    NULL,
    NULL
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = COALESCE(methods.code_snippet_url, EXCLUDED.code_snippet_url),
    image_url = COALESCE(methods.image_url, EXCLUDED.image_url),
    image_credit = COALESCE(methods.image_credit, EXCLUDED.image_credit),
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'gpt-4'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

WITH gpt3 AS (
    SELECT id
    FROM papers
    WHERE arxiv_id = '2005.14165'
      AND is_latest_version
    ORDER BY id DESC
    LIMIT 1
),
gpt4 AS (
    SELECT id
    FROM papers
    WHERE arxiv_id = '2303.08774'
      AND is_latest_version
    ORDER BY id DESC
    LIMIT 1
)
INSERT INTO paper_relations (source_paper_id, target_paper_id)
SELECT gpt3.id, gpt4.id
FROM gpt3, gpt4
ON CONFLICT DO NOTHING;

COMMIT;
