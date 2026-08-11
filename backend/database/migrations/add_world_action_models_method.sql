-- World Action Models (WAMs) — predictive world modeling coupled to robot action generation.
-- Taxonomy source: arXiv 2605.12090

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
    'world-action-models',
    'World Action Models',
    'World Action Models (WAMs)',
    'World Action Models (WAMs) are embodied predictive-action models that combine world modeling with robot control. They predict or represent task-relevant future states and couple those predictions to executable actions, either through cascaded imagine-then-act pipelines or joint world-and-action generation. Unlike [Vision-Language-Action models](/methods/vla), which may map observations and instructions directly to actions, WAMs explicitly make modeled future dynamics available to the policy.',
    'World Action Model, World Action Models, WAM, WAMs, world-action model, world-action models, predictive-action model, predictive-action models',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2026,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2605.12090'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'World Action Models: The Next Frontier in Embodied AI',
    NULL,
    NULL,
    '[World Action Models: The Next Frontier in Embodied AI](/paper/2605.12090)'
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
SELECT source_paper_id, id FROM methods
WHERE slug = 'world-action-models' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
