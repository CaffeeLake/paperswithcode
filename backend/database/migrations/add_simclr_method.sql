-- Add SimCLR (Simple Framework for Contrastive Learning of Visual Representations).
-- Source paper: arXiv 2002.05709

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'simclr',
    'SimCLR',
    'Simple Framework for Contrastive Learning of Visual Representations (SimCLR)',
    'SimCLR is a self-supervised framework for learning visual representations from two stochastic augmented views of each image. A [ResNet](/methods/resnet) encoder and nonlinear projection head are trained with a normalized temperature-scaled contrastive objective that maximizes agreement between matching views while treating other augmented samples in the batch as negatives. Its results established strong data augmentation, a projection head, and large batches as key ingredients for contrastive representation learning, reaching 76.5% ImageNet top-1 accuracy under linear evaluation with a ResNet-50.',
    'SimCLR, sim-clr, Simple Framework for Contrastive Learning of Visual Representations, contrastive learning, self-supervised learning, visual representation learning, NT-Xent',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2020,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2002.05709'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Simple Framework for Contrastive Learning of Visual Representations',
    'https://github.com/google-research/simclr',
    NULL,
    '[A Simple Framework for Contrastive Learning of Visual Representations](/paper/2002.05709)'
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
WHERE slug = 'simclr' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
