-- Point speculative-decoding figure credit to the local survey paper page.
UPDATE methods
SET
    image_credit = '[Unlocking Efficiency in Large Language Model Inference: A Comprehensive Survey of Speculative Decoding](/paper/2401.07851)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'speculative-decoding';
