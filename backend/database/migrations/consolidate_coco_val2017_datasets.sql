-- Migration: Consolidate duplicate COCO val2017 datasets
-- Problem: We have two datasets for the same thing:
--   - ID 6: "COCO val2017"
--   - ID 7: "COCO 2017 val"
-- Both refer to COCO 2017 validation split
--
-- Solution: Keep ID 6, migrate all references from ID 7 to ID 6, then delete ID 7

-- Step 1: Show current state
SELECT 'Current datasets:' as step;
SELECT id, name, full_name, parent_dataset_id, variant_type, split_name
FROM datasets
WHERE id IN (6, 7);

SELECT 'Current evaluations using these datasets:' as step;
SELECT e.id, e.paper_id, e.dataset_id, d.name, p.arxiv_id
FROM evaluations e
JOIN datasets d ON e.dataset_id = d.id
JOIN papers p ON e.paper_id = p.id
WHERE e.dataset_id IN (6, 7)
ORDER BY e.dataset_id, e.id;

-- Step 2: Update all evaluations that reference dataset 7 to reference dataset 6
UPDATE evaluations
SET dataset_id = 6
WHERE dataset_id = 7;

SELECT 'After migration - evaluations now using dataset 6:' as step;
SELECT e.id, e.paper_id, e.dataset_id, d.name, p.arxiv_id
FROM evaluations e
JOIN datasets d ON e.dataset_id = d.id
JOIN papers p ON e.paper_id = p.id
WHERE e.dataset_id = 6
ORDER BY e.id;

-- Step 3: Delete the duplicate dataset entry
DELETE FROM datasets WHERE id = 7;

SELECT 'Remaining COCO validation datasets:' as step;
SELECT id, name, full_name, parent_dataset_id, variant_type, split_name
FROM datasets
WHERE name ILIKE '%coco%' AND name ILIKE '%val%'
ORDER BY id;

SELECT 'Migration complete!' as step;
