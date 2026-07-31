-- Add the Looped Transformer method and link the curated alphaXiv collection.
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
    'looped-transformer',
    'Looped Transformer',
    'Looped Transformer',
    'Looped Transformers reuse one or more [Transformer](/methods/transformer) blocks across recurrent depth, decoupling effective computation depth from parameter count and enabling iterative refinement, adaptive computation, and test-time depth scaling. The family spans recurrent-depth language models, reasoning systems, diffusion and visual generators, and world models.',
    'looped transformer, looping transformer, looped language model, recurrent-depth transformer, depth-recurrent transformer',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1807.03819'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Universal Transformers',
    NULL,
    NULL,
    '[Universal Transformers](/paper/1807.03819)'
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
SELECT collection_papers.id, method.id
FROM (
    SELECT DISTINCT ON (arxiv_id) id
    FROM papers
    WHERE arxiv_id IN (
        '1807.03819',
        '2405.16039',
        '2410.20672',
        '2502.05171',
        '2507.10524',
        '2510.25741',
        '2604.07822',
        '2604.09168',
        '2604.11791',
        '2604.12946',
        '2604.21254',
        '2605.07721',
        '2605.12466',
        '2605.20670',
        '2605.23872',
        '2605.26106',
        '2606.18206',
        '2606.18208',
        '2606.31779',
        '2607.13491'
    )
    ORDER BY arxiv_id, is_latest_version DESC, id DESC
) AS collection_papers
CROSS JOIN (
    SELECT id
    FROM methods
    WHERE slug = 'looped-transformer'
) AS method
ON CONFLICT (paper_id, method_id) DO NOTHING;
