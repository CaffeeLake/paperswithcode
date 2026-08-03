-- Add Recursive Self-Improvement (RSI) and link a manually reviewed collection
-- spanning foundational work, direct RSI systems, and substantive RSI analyses.

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'recursive-self-improvement',
    'Recursive Self-Improvement',
    'Recursive Self-Improvement (RSI)',
    'Recursive Self-Improvement (RSI) is a class of AI systems that iteratively improve the mechanisms responsible for producing their own successors, allowing gains in the system to strengthen the process that generates further gains. Modern work studies bounded forms through self-modifying agents, automated AI research, executable feedback, and repeated training or search loops.',
    'recursive self-improvement, recursive self improvement, recursively self-improving, recursively self improving, recursive self-improving, recursive self improving',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1805.06610'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Formulation of Recursive Self-Improvement and Its Possible Efficiency',
    NULL,
    NULL,
    '[A Formulation of Recursive Self-Improvement and Its Possible Efficiency](/paper/1805.06610)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT curated_papers.id, method.id
FROM (
    SELECT DISTINCT ON (arxiv_id) id
    FROM papers
    WHERE arxiv_id IN (
        'cs/0309048',
        '1312.6764',
        '1410.0369',
        '1805.06610',
        '2202.05780',
        '2205.00167',
        '2309.16797',
        '2310.02304',
        '2406.18532',
        '2408.08435',
        '2410.04444',
        '2410.12375',
        '2411.16905',
        '2502.00757',
        '2504.15228',
        '2505.22954',
        '2506.04651',
        '2510.21614',
        '2511.13646',
        '2512.18746',
        '2602.04837',
        '2602.15659',
        '2602.22480',
        '2603.06333',
        '2603.18073',
        '2603.19461',
        '2603.29640',
        '2604.15034',
        '2604.21003',
        '2605.15871',
        '2605.27276',
        '2606.04455',
        '2606.12683',
        '2606.14249',
        '2606.26294',
        '2607.05297',
        '2607.05382',
        '2607.07663',
        '2607.12254',
        '2607.12625',
        '2607.13104',
        '2607.15524',
        '2607.21461',
        '2607.27191',
        '2607.28568'
    )
    ORDER BY arxiv_id, is_latest_version DESC, id DESC
) AS curated_papers
CROSS JOIN (
    SELECT id
    FROM methods
    WHERE slug = 'recursive-self-improvement'
) AS method
WHERE NOT EXISTS (
    SELECT 1
    FROM paper_method_exclusions exclusion
    WHERE exclusion.paper_id = curated_papers.id
      AND exclusion.method_id = method.id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

WITH curated_papers AS (
    SELECT DISTINCT ON (p.arxiv_id) p.id AS paper_id, m.id AS method_id
    FROM papers p
    CROSS JOIN methods m
    WHERE p.arxiv_id IN (
        'cs/0309048',
        '1312.6764',
        '1410.0369',
        '1805.06610',
        '2202.05780',
        '2205.00167',
        '2309.16797',
        '2310.02304',
        '2406.18532',
        '2408.08435',
        '2410.04444',
        '2410.12375',
        '2411.16905',
        '2502.00757',
        '2504.15228',
        '2505.22954',
        '2506.04651',
        '2510.21614',
        '2511.13646',
        '2512.18746',
        '2602.04837',
        '2602.15659',
        '2602.22480',
        '2603.06333',
        '2603.18073',
        '2603.19461',
        '2603.29640',
        '2604.15034',
        '2604.21003',
        '2605.15871',
        '2605.27276',
        '2606.04455',
        '2606.12683',
        '2606.14249',
        '2606.26294',
        '2607.05297',
        '2607.05382',
        '2607.07663',
        '2607.12254',
        '2607.12625',
        '2607.13104',
        '2607.15524',
        '2607.21461',
        '2607.27191',
        '2607.28568'
    )
      AND p.is_latest_version
      AND m.slug = 'recursive-self-improvement'
      AND NOT EXISTS (
          SELECT 1
          FROM paper_method_exclusions exclusion
          WHERE exclusion.paper_id = p.id
            AND exclusion.method_id = m.id
      )
    ORDER BY p.arxiv_id, p.id DESC
)
INSERT INTO paper_method_evidence (
    paper_id,
    method_id,
    evidence_type,
    details
)
SELECT
    paper_id,
    method_id,
    'manual',
    '{"reason":"Manually reviewed for direct RSI relevance or substantive RSI discussion"}'::jsonb
FROM curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now(),
    details = EXCLUDED.details;
