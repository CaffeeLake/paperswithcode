-- Migration: Seed DeepSeek paper lineage relations
--
-- Records the core DeepSeek model-report lineage as direct predecessor ->
-- successor edges. The UI/API surface these rows as predecessor_papers and
-- successor_papers on paper detail pages.
--
-- Created: 2026-05-23

BEGIN;

WITH deepseek_papers(label, paper_id) AS (
    SELECT 'v1', id
    FROM papers
    WHERE arxiv_id = '2401.02954'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
deepseek_papers_v2(label, paper_id) AS (
    SELECT 'v2', id
    FROM papers
    WHERE arxiv_id = '2405.04434'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
deepseek_papers_v3(label, paper_id) AS (
    SELECT 'v3', id
    FROM papers
    WHERE arxiv_id = '2412.19437'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
deepseek_papers_r1(label, paper_id) AS (
    SELECT 'r1', id
    FROM papers
    WHERE arxiv_id = '2501.12948'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
deepseek_papers_v4(label, paper_id) AS (
    SELECT 'v4', id
    FROM papers
    WHERE source = 'external'
      AND title = 'DeepSeek-V4: Towards Highly Efficient Million-Token Context Intelligence'
      AND is_latest_version
    ORDER BY id
    LIMIT 1
),
all_deepseek_papers AS (
    SELECT * FROM deepseek_papers
    UNION ALL
    SELECT * FROM deepseek_papers_v2
    UNION ALL
    SELECT * FROM deepseek_papers_v3
    UNION ALL
    SELECT * FROM deepseek_papers_r1
    UNION ALL
    SELECT * FROM deepseek_papers_v4
),
lineage(source_label, target_label) AS (
    VALUES
        ('v1', 'v2'),
        ('v2', 'v3'),
        ('v3', 'r1'),
        ('r1', 'v4')
)
INSERT INTO paper_relations (source_paper_id, target_paper_id)
SELECT source.paper_id, target.paper_id
FROM lineage
JOIN all_deepseek_papers source ON source.label = lineage.source_label
JOIN all_deepseek_papers target ON target.label = lineage.target_label
ON CONFLICT DO NOTHING;

COMMIT;
