-- Add Watermarking method.
-- Cross-domain technique for embedding detectable signals in AI-generated content.
-- Thumbnail figure from arXiv 2301.10226 (LLM watermarking).

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
    'watermarking',
    'Watermarking',
    'Watermarking',
    'Watermarking embeds imperceptible, algorithmically detectable signals into AI-generated content—text, images, audio, video, or model weights—to support provenance, attribution, copyright protection, and misuse detection. Modern approaches include LLM samplers that bias token logits toward detectable patterns, latent-space fingerprints for [Diffusion](/methods/diffusion) models, and robust marks in pixel or spectral domains. Detection can often run without access to model parameters, making watermarking a practical tool for tracing synthetic media at scale.',
    'Watermarking, watermark, invisible watermark, AI watermarking, LLM watermarking, image watermarking, model watermarking, text watermarking, digital watermarking',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    NULL,
    NULL,
    'https://github.com/jwkirchenbauer/lm-watermarking',
    'https://paperswithcode.co/images/methods/watermarking.png',
    '[A Watermark for Large Language Models](/paper/2301.10226)'
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
