-- Add Sliding Window Attention as a curated method.
--
-- There is no single canonical "source" paper for the method in this project;
-- the source fields intentionally point at a clear explainer with diagrams and
-- runnable examples.

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'sliding-window-attention',
    'Sliding window attention',
    'Sliding Window Attention (SWA)',
    'A local attention pattern that restricts each token to attending only within a fixed-size neighborhood instead of the full sequence. This reduces attention and KV-cache memory for long-context models while periodic global-attention layers can preserve broader context.',
    'sliding window attention, sliding-window attention, SWA, local attention, sliding window self-attention',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2020,
    'https://github.com/rasbt/LLMs-from-scratch/tree/main/ch04/06_swa',
    'Sliding Window Attention (SWA)',
    'https://github.com/rasbt/LLMs-from-scratch/blob/main/ch04/06_swa/gpt_with_kv_swa.py',
    'https://sebastianraschka.com/images/LLMs-from-scratch-images/bonus/swa-memory/1.webp?2',
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
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;
