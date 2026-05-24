-- Add Grouped-Query Attention as a curated method.
--
-- The canonical source is the local GQA paper row. The Raschka links provide
-- display-friendly explanatory code and imagery.

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
    'grouped-query-attention',
    'Grouped-Query Attention',
    'Grouped-Query Attention (GQA)',
    'An attention mechanism that lets multiple query heads share fewer key and value heads, sitting between multi-head attention and multi-query attention. By reducing the number of key/value projections and KV-cache tensors, GQA lowers memory bandwidth and inference memory while preserving much of the modeling quality of standard multi-head attention.',
    'Grouped-Query Attention, Grouped Query Attention, GQA, grouped-query attention, generalized multi-query attention, key-value head sharing, KV cache, multi-query attention',
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
        WHERE arxiv_id = '2305.13245'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints',
    'https://github.com/rasbt/LLMs-from-scratch/blob/main/ch04/04_gqa/gpt_with_kv_gqa.py',
    'https://sebastianraschka.com/images/LLMs-from-scratch-images/bonus/gqa-memory/1.webp?1',
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
WHERE slug = 'grouped-query-attention'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
