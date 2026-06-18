-- Diffusion Policy — visuomotor policy learning via action diffusion (Chi et al., 2023).
-- Source paper: arXiv 2303.04137

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
    'diffusion-policy',
    'Diffusion Policy',
    'Diffusion Policy',
    'Diffusion Policy learns visuomotor robot policies by denoising action trajectories conditioned on visual observations. It treats action sequences as targets for a diffusion model, enabling stable multi-step [Imitation learning](/methods/imitation-learning) on contact-rich manipulation tasks such as Push-T, RoboMimic suites, and real-robot tool use. The approach influenced later action-chunking and VLA systems that combine diffusion with language conditioning.',
    'Diffusion Policy, diffusion policy, action diffusion, visuomotor diffusion',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2303.04137'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Diffusion Policy: Visuomotor Policy Learning via Action Diffusion',
    'https://github.com/real-stanford/diffusion_policy',
    NULL,
    '[Diffusion Policy: Visuomotor Policy Learning via Action Diffusion](/paper/2303.04137)'
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
WHERE slug = 'diffusion-policy' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
