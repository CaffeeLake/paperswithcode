-- Migration: Remove duplicate ViT method
-- Description: Merge paper links from the duplicate `vit` method into canonical
-- `vision-transformer`, then delete `vit`.
-- Date: 2026-05-09

WITH canonical AS (
    SELECT id
    FROM methods
    WHERE slug = 'vision-transformer'
),
duplicate AS (
    SELECT id
    FROM methods
    WHERE slug = 'vit'
),
transferred AS (
    INSERT INTO paper_methods (paper_id, method_id)
    SELECT pm.paper_id, canonical.id
    FROM paper_methods pm
    CROSS JOIN canonical
    JOIN duplicate
        ON duplicate.id = pm.method_id
    ON CONFLICT DO NOTHING
    RETURNING paper_id, method_id
),
removed AS (
    DELETE FROM methods m
    USING duplicate, canonical
    WHERE m.id = duplicate.id
    RETURNING m.id
)
SELECT
    (SELECT count(*) FROM transferred) AS paper_methods_transferred,
    (SELECT count(*) FROM removed) AS duplicate_methods_removed;
