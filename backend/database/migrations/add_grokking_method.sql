-- Grokking (delayed generalization) — training phenomenon introduced by Power et al., 2022.
-- Source paper: arXiv 2201.02177

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
    'grokking',
    'Grokking',
    'Grokking (Delayed Generalization)',
    'Grokking is a training phenomenon in which a model abruptly transitions from overfitting (high training accuracy, poor held-out performance) to generalizing after many optimization steps with little or no test improvement — unlike the gradual co-improvement usually seen in machine learning. The term was introduced by Power et al. (2022) on small algorithmic tasks such as modular arithmetic, and follow-up work interprets grokking as a phase transition during training, often linked to weight decay, optimizer dynamics, and a shift from lazy to rich learning regimes.',
    'Grokking, grokking, delayed generalization, delayed-generalization',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2022,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2201.02177'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Grokking: Generalization Beyond Overfitting on Small Algorithmic Datasets',
    NULL,
    NULL,
    '[Grokking: Generalization Beyond Overfitting on Small Algorithmic Datasets](/paper/2201.02177)'
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
WHERE slug = 'grokking' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
