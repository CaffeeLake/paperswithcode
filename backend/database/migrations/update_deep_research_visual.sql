UPDATE methods
SET
    image_credit = '[Introducing deep research](https://openai.com/index/introducing-deep-research/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'deep-research';
