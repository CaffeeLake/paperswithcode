-- Use a single keyword phrase for neural-audio-codec tagging.

UPDATE methods
SET
    keywords = 'neural audio codec',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'neural-audio-codec';
