-- Migration: Seed RT-DETR paper lineage relations
--
-- Records RT-DETRv2 as the direct successor of the original RT-DETR paper.
--
-- Created: 2026-05-23

BEGIN;

WITH rtdetr AS (
    SELECT id
    FROM papers
    WHERE arxiv_id = '2304.08069'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
rtdetr_v2 AS (
    SELECT id
    FROM papers
    WHERE arxiv_id = '2407.17140'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
)
INSERT INTO paper_relations (source_paper_id, target_paper_id)
SELECT rtdetr.id, rtdetr_v2.id
FROM rtdetr, rtdetr_v2
ON CONFLICT DO NOTHING;

COMMIT;
