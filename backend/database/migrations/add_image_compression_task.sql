-- Add Image Compression as a top-level Vision task.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Image Compression',
    'image-compression',
    'Image compression encodes images into compact bitstreams and reconstructs them while balancing bitrate, visual quality, and computational cost. Modern approaches learn transforms, entropy models, quantizers, and generative decoders for lossy or lossless coding, complementing [Image Restoration](/tasks/image-restoration) when compression artifacts must subsequently be removed.',
    'learned image compression, neural image compression, generative image compression, perceptual image compression, lossless image compression, lossy image compression, transformer-based image compression, image compression model, image compression method, image compression framework, image compression algorithm, image compression system, image compression codec, end-to-end image compression, image compression for machines, image compression for machine perception',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Transformer-based Image Compression](/paper/2111.06707)',
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
