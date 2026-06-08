-- Mark RoPE as introduced by the RoFormer paper.
-- Source paper: arXiv 2104.09864

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
    'rope',
    'RoPE',
    'Rotary Position Embedding (RoPE)',
    'Rotary Position Embedding (RoPE) adds positional information to Transformer models by rotating query and key vectors inside the self-attention mechanism. Instead of adding positional vectors to token representations, RoPE rotates paired vector dimensions by a position-dependent angle, so query-key dot products naturally encode relative distance between tokens.',
    'RoPE, Rotary Position Embedding, Rotary Positional Encoding, rotary position embedding, rotary positional embedding, rotary embeddings',
    (
        SELECT id
        FROM areas
        WHERE name IN ('General', 'Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'General' THEN 0 WHEN 'Language' THEN 1 ELSE 2 END
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2104.09864'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'RoFormer: Enhanced Transformer with Rotary Position Embedding',
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
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'rope'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
