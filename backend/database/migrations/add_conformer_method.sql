-- Add Conformer (Convolution-augmented Transformer) method.
-- Source paper: arXiv 2005.08100

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
    'conformer',
    'Conformer',
    'Conformer (Convolution-augmented Transformer)',
    'Conformer is a convolution-augmented [Transformer](/methods/transformer) encoder for automatic speech recognition that combines global self-attention with local depthwise convolutions. Each Conformer block uses a Macaron-style layout—two half-step feed-forward modules sandwiching multi-head self-attention and a convolution module—so the model captures both long-range context and local spectral patterns in a parameter-efficient way. It set LibriSpeech state-of-the-art word error rates when introduced in 2020.',
    'Conformer, conformer, convolution-augmented transformer, convolution augmented transformer',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2005.08100'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Conformer: Convolution-augmented Transformer for Speech Recognition',
    'https://github.com/espnet/espnet/blob/master/espnet2/asr/encoder/conformer_encoder.py',
    'https://paperswithcode.co/images/methods/conformer.png',
    '[Conformer: Convolution-augmented Transformer for Speech Recognition](/paper/2005.08100)'
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
WHERE slug = 'conformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
