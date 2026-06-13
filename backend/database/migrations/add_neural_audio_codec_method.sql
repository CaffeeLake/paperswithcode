-- Add Neural Audio Codec (learned end-to-end compression) method.
-- General technique category; SoundStream is an example instance, not the source.

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
    'neural-audio-codec',
    'Neural Audio Codec',
    'Neural Audio Codec (Learned End-to-End Compression)',
    'A neural audio codec uses learned encoder–decoder models to compress audio into a compact representation and reconstruct it at decode time, often replacing handcrafted stages in classical codecs. That compression reduces bandwidth and storage for streaming, telephony, and on-device playback, and yields compact codes that are easier to transmit or feed into downstream speech and audio models. Implementations may use continuous latents, vector quantization, or other bottlenecks depending on bitrate and latency needs. [SoundStream](/methods/soundstream) is a widely used example for low-latency speech and general audio.',
    'neural audio codec',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    NULL,
    NULL,
    NULL,
    NULL,
    'https://github.com/facebookresearch/encodec',
    'https://paperswithcode.co/images/methods/neural-audio-codec.png',
    '[SoundStream](/methods/soundstream)'
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
