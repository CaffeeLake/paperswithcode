-- Neural Audio Codec is a general technique, not tied to a single introducing paper.

UPDATE methods
SET
    source_paper_id = NULL,
    source_url = NULL,
    source_title = NULL,
    introduced_year = NULL,
    image_credit = '[SoundStream](/methods/soundstream)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'neural-audio-codec';

DELETE FROM paper_methods
WHERE method_id = (SELECT id FROM methods WHERE slug = 'neural-audio-codec');
