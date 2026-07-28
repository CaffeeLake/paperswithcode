-- Add Video Compression as a top-level Video task.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Compression',
    'video-compression',
    'Video compression encodes frame sequences into compact bitstreams or latent tokens and reconstructs them while balancing bitrate, spatial detail, temporal consistency, and computational cost. Modern approaches include learned video codecs, causal video autoencoders, and discrete video tokenizers used for storage, transmission, and efficient [Video Generation](/tasks/video-generation).',
    'video compression, learned video compression, neural video compression, generative video compression, perceptual video compression, lossless video compression, lossy video compression, video coding, learned video coding, neural video coding, video codec, neural video codec, video compression model, video compression method, video compression framework, video compression algorithm, end-to-end video compression, video tokenizer, video tokenization, discrete video tokenizer, adaptive video tokenization, video autoencoder, video VAE, video rate-distortion',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[InfoTok: Adaptive Discrete Video Tokenizer via Information-Theoretic Compression](/paper/2512.16975)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
