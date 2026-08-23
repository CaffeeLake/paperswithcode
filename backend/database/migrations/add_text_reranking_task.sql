-- Add text reranking as a retrieval subtask and reuse the existing MTEB v2
-- benchmark row. The MTEB leaderboard's Rerank column is the task metric.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Text Reranking',
    'text-reranking',
    'Text reranking orders a candidate set of passages, documents, or records by relevance to a query, usually after an initial retrieval stage. Rerankers commonly score query-document pairs with cross-encoders or late-interaction models to improve the final ranking in [Retrieval](/tasks/retrieval), semantic search, question answering, and retrieval-augmented generation systems.',
    'text reranking, text re-ranking, reranking, re-ranking, neural reranking, neural re-ranking, document reranking, passage reranking, query-document reranking, query document reranking, cross-encoder reranking, cross encoder reranking, learning to rerank, ranker, reranker',
    (SELECT area_id FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    TRUE,
    NULL,
    'Papers With Code',
    'https://huggingface.co/spaces/mteb/leaderboard'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES (
    'Rerank',
    'MTEB Rerank Score',
    'higher_is_better',
    '0-100',
    'The aggregate reranking score reported in the Rerank column of the MTEB leaderboard; higher scores indicate better ordering of candidates by query relevance.'
)
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    scale = EXCLUDED.scale,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

-- MTEB (English, v2) is already the canonical MTEB benchmark used for
-- embedding models. Reuse it for the reranking leaderboard rather than
-- introducing a duplicate dataset row.
INSERT INTO task_datasets (task_id, dataset_id)
SELECT t.id, d.id
FROM tasks t
JOIN datasets d ON d.slug = 'mteb'
WHERE t.slug = 'text-reranking'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'mteb'
JOIN metrics m ON m.name = 'Rerank'
WHERE t.slug = 'text-reranking'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- MTEB (English, v2) is described by MMTEB. Retain a manual source-paper
-- task association so it survives automatic keyword linking rebuilds.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'text-reranking'
WHERE p.arxiv_id = '2502.13595'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
