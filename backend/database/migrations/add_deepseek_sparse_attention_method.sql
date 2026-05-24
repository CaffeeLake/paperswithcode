-- Add DeepSeek Sparse Attention as a curated method.
--
-- The source paper points at the local DeepSeek-V3.2 paper row. The image and
-- code fields keep the explainer/example links used for display.

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
    'deepseek-sparse-attention',
    'DeepSeek Sparse Attention',
    'DeepSeek Sparse Attention (DSA)',
    'A learned sparse attention mechanism from DeepSeek-V3.2 that scores candidate past tokens with a lightweight indexer, keeps the top-k most relevant positions, and masks the rest before the attention softmax. In production implementations this can reduce long-context attention work from dense all-pairs attention toward O(L*k) while retaining access to non-local tokens.',
    'DeepSeek Sparse Attention, DSA, sparse attention, learned sparse attention, top-k attention, lightning indexer, token selector',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2512.02556'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DeepSeek-V3.2: Pushing the Frontier of Open Large Language Models',
    'https://github.com/rasbt/LLMs-from-scratch/blob/main/ch04/09_dsa/gpt_with_kv_dsa.py',
    'https://sebastianraschka.com/images/blog/2025/technical-deepseek/10.png',
    'Sebastian Raschka, LLMs-from-scratch'
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'deepseek-sparse-attention'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
