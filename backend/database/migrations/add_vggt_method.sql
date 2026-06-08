-- Add VGGT (Visual Geometry Grounded Transformer) method.
-- Source paper: arXiv 2503.11651

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
    'vggt',
    'VGGT',
    'Visual Geometry Grounded Transformer (VGGT)',
    'VGGT is a large feed-forward [Transformer](/methods/transformer) that directly infers key 3D scene attributes — camera parameters, depth maps, point maps, and 3D point tracks — from one, a few, or hundreds of input views in a single forward pass. Unlike optimization-heavy pipelines and earlier feed-forward approaches such as [DUSt3R](/methods/dust3r), VGGT often produces usable geometry without costly iterative post-processing, making fast and versatile 3D reconstruction practical at scale.',
    'VGGT, Visual Geometry Grounded Transformer, visual geometry grounded transformer, vgg-t',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2503.11651'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'VGGT: Visual Geometry Grounded Transformer',
    'https://github.com/facebookresearch/vggt',
    'https://paperswithcode.co/images/methods/vggt.png',
    '[VGGT: Visual Geometry Grounded Transformer](/paper/2503.11651)'
)
ON CONFLICT (slug) DO UPDATE
SET
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'vggt'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
