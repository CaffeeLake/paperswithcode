-- Migration: Add directed paper-to-paper relations (predecessor/successor)
--
-- Creates the `paper_relations` junction table to record directed lineage
-- edges between papers, e.g. DINOv2 -> DINOv3 ("X is the predecessor of Y" /
-- "Y is the successor of X"). The relationship is many-to-many in both
-- directions: a paper may have multiple successors (follow-up papers) and
-- multiple predecessors.
--
--   source_paper_id -> the earlier paper (predecessor)
--   target_paper_id -> the later paper (successor)
--
-- A self-edge is forbidden via CHECK constraint. Both columns cascade on
-- paper delete to keep referential integrity.
--
-- The migration also seeds the canonical DINOv2 -> DINOv3 edge when both
-- arXiv papers (`2304.07193` and `2508.10104`) already exist in the DB.
--
-- Created: 2026-05-22
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_paper_relations.sql

BEGIN;

CREATE TABLE IF NOT EXISTS paper_relations (
    source_paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    target_paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_paper_id, target_paper_id),
    CONSTRAINT paper_relations_no_self_link CHECK (source_paper_id <> target_paper_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_relations_source_paper_id
    ON paper_relations(source_paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_relations_target_paper_id
    ON paper_relations(target_paper_id);

COMMENT ON TABLE paper_relations IS
'Directed lineage edges between papers. source_paper_id is the predecessor (earlier) paper; target_paper_id is the successor (follow-up) paper.';

-- Seed DINOv2 -> DINOv3 if both rows already exist (latest version preferred).
WITH dinov2 AS (
    SELECT id FROM papers
    WHERE arxiv_id = '2304.07193' AND is_latest_version
    ORDER BY id
    LIMIT 1
),
dinov3 AS (
    SELECT id FROM papers
    WHERE arxiv_id = '2508.10104' AND is_latest_version
    ORDER BY id
    LIMIT 1
)
INSERT INTO paper_relations (source_paper_id, target_paper_id)
SELECT d2.id, d3.id
FROM dinov2 d2, dinov3 d3
ON CONFLICT DO NOTHING;

COMMIT;
