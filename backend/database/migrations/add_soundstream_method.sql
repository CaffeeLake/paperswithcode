-- Add SoundStream (end-to-end neural audio codec) method.
-- Source paper: arXiv 2107.03312

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
    'soundstream',
    'SoundStream',
    'SoundStream (End-to-End Neural Audio Codec)',
    'SoundStream is an end-to-end [neural audio codec](/methods/neural-audio-codec) that jointly trains a fully convolutional encoder/decoder with a residual vector quantizer (RVQ) using reconstruction and adversarial losses. A single model supports variable bitrates from 3–18 kbps via quantizer dropout, runs with low latency on mobile CPUs, and can jointly compress and enhance audio (e.g. background noise suppression) without extra delay. At 24 kHz, SoundStream at 3 kbps outperforms Opus at 12 kbps in subjective tests and approaches EVS at 9.6 kbps.',
    'SoundStream, soundstream, neural audio codec, end-to-end audio codec, RVQ, residual vector quantizer',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2107.03312'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'SoundStream: An End-to-End Neural Audio Codec',
    'https://github.com/lucidrains/audiolm-pytorch/blob/main/audiolm_pytorch/soundstream.py',
    'https://paperswithcode.co/images/methods/soundstream.png',
    '[SoundStream: An End-to-End Neural Audio Codec](/paper/2107.03312)'
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
WHERE slug = 'soundstream'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
