-- Credit the curated architecture figure to the introducing paper.
UPDATE methods
SET
    image_credit = '[Gated DeltaNet-2: Decoupling Erase and Write in Linear Attention](/paper/2605.22791)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gated-deltanet-2';
