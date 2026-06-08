-- Update RLHF method visual to the three-stage pipeline diagram from the InstructGPT paper.
UPDATE methods
SET
    image_url = 'https://paperswithcode.co/images/methods/rlhf.png',
    image_credit = '[Training language models to follow instructions with human feedback](/paper/2203.02155)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'rlhf';
