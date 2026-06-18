-- ACT (Action Chunking with Transformers) — bimanual imitation learning (Zhao et al., 2023).
-- Source paper: arXiv 2304.13705

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
    'act',
    'ACT',
    'Action Chunking with Transformers (ACT)',
    'ACT is an [Imitation learning](/methods/imitation-learning) architecture that predicts short action chunks with a conditional VAE transformer, enabling precise bimanual manipulation on ALOHA-style platforms. By modeling temporally extended action sequences instead of single-step commands, ACT reduces compounding errors on contact-rich tasks and became a standard baseline for sim and real-robot teleoperation benchmarks.',
    'ACT, Action Chunking with Transformers, action chunking transformer, action chunking',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2304.13705'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware',
    'https://github.com/tonyzhaozh/act',
    NULL,
    '[Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware](/paper/2304.13705)'
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
WHERE slug = 'act' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
