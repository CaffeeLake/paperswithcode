-- Add Fast Conformer method.
-- Source paper: arXiv 2305.05084

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
    'fast-conformer',
    'Fast Conformer',
    'Fast Conformer (FC)',
    'Fast Conformer is a redesigned [Conformer](/methods/conformer) encoder for efficient speech recognition that keeps the same block structure while changing the front-end subsampling to 8× depthwise-separable convolutions and smaller kernels. That cuts encoder compute by about 2.8× versus the original Conformer while matching or improving ASR accuracy. The same architecture can also switch to linearly scalable limited-context attention with an optional global token, enabling long-form transcription without quadratic attention cost.',
    'Fast Conformer, FastConformer, fast conformer, fast-conformer',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2305.05084'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Fast Conformer with Linearly Scalable Attention for Efficient Speech Recognition',
    'https://github.com/NVIDIA/NeMo/blob/main/nemo/collections/asr/modules/conformer_encoder.py',
    'https://paperswithcode.co/images/methods/fast-conformer.png',
    '[Fast Conformer with Linearly Scalable Attention for Efficient Speech Recognition](/paper/2305.05084)'
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
WHERE slug = 'fast-conformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
