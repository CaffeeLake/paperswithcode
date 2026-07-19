-- Scene Text Recognition task hero: detection and recognition pipeline diagram.
UPDATE tasks
SET
    image_url = NULL,
    image_credit = '[Scene Text Detection and Recognition: The Deep Learning Era](https://link.springer.com/article/10.1007/s11263-020-01369-0)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'scene-text-recognition';
