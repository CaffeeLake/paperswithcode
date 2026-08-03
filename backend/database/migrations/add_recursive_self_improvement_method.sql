-- Add Recursive Self-Improvement (RSI) and link papers with manually reviewed,
-- unambiguous phrase matches in their title or abstract.

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
        '1805.06610',
        '2202.05780',
        '2310.02304',
        '2410.04444',
        '2410.12375',
        '2411.16905',
        '2602.15659',
        '2603.06333',
        '2605.15871',
        '2606.04455',
        '2607.05382',
        '2607.12625',
        '2607.21461',
        '2607.28568'
    )
    ORDER BY arxiv_id, is_latest_version DESC, id DESC
) AS curated_papers
CROSS JOIN (
    SELECT id
    FROM methods
    WHERE slug = 'recursive-self-improvement'
) AS method
ON CONFLICT (paper_id, method_id) DO NOTHING;
