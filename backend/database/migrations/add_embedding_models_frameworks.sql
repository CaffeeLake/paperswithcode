-- Add embedding-focused frameworks and recommend them on the Embedding models task.

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES
    (
        'https://github.com/huggingface/sentence-transformers',
        'huggingface',
        'sentence-transformers',
        0,
        'framework_catalog'
    ),
    (
        'https://github.com/vllm-project/vllm',
        'vllm-project',
        'vllm',
        0,
        'framework_catalog'
    ),
    (
        'https://github.com/huggingface/text-embeddings-inference',
        'huggingface',
        'text-embeddings-inference',
        0,
        'framework_catalog'
    )
ON CONFLICT (url) DO UPDATE SET
    owner = EXCLUDED.owner,
    name = EXCLUDED.name;

WITH framework_data(
    category_slug, slug, name, organization_name, description, when_to_use,
    github_url, docs_url, paper_arxiv_id, display_order
) AS (
    VALUES
        (
            'model-libraries',
            'sentence-transformers',
            'Sentence Transformers',
            'Hugging Face',
            'A Python library for training and using embedding and reranker models for semantic search, retrieval, clustering, and similarity.',
            'Train, fine-tune, or evaluate text and multimodal embedding models through a high-level PyTorch interface.',
            'https://github.com/huggingface/sentence-transformers',
            'https://sbert.net/',
            '1908.10084',
            1
        ),
        (
            'inference',
            'text-embeddings-inference',
            'Text Embeddings Inference',
            'Hugging Face',
            'A high-performance server for text embedding, reranking, and sequence-classification models.',
            'Serve embedding or reranker models with production-oriented batching, optimized kernels, and an HTTP API.',
            'https://github.com/huggingface/text-embeddings-inference',
            'https://huggingface.co/docs/text-embeddings-inference/',
            NULL,
            6
        )
)
INSERT INTO frameworks (
    category_id, repository_id, introducing_paper_id, slug, name,
    organization_name, description, when_to_use, docs_url, display_order
)
SELECT
    category.id,
    repository.id,
    paper.id,
    framework.slug,
    framework.name,
    framework.organization_name,
    framework.description,
    framework.when_to_use,
    framework.docs_url,
    framework.display_order
FROM framework_data framework
JOIN framework_domains domain ON domain.slug = 'llm'
JOIN framework_categories category
    ON category.domain_id = domain.id
    AND category.slug = framework.category_slug
JOIN repositories repository ON repository.url = framework.github_url
LEFT JOIN LATERAL (
    SELECT papers.id
    FROM papers
    WHERE papers.arxiv_id = framework.paper_arxiv_id
      AND papers.is_latest_version
    ORDER BY papers.id DESC
    LIMIT 1
) paper ON true
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    introducing_paper_id = COALESCE(
        EXCLUDED.introducing_paper_id,
        frameworks.introducing_paper_id
    ),
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

WITH platform_data(framework_slug, platform) AS (
    VALUES
        ('sentence-transformers', 'gpu'),
        ('sentence-transformers', 'cpu'),
        ('sentence-transformers', 'apple'),
        ('text-embeddings-inference', 'gpu'),
        ('text-embeddings-inference', 'cpu')
)
INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, platform.platform
FROM platform_data platform
JOIN frameworks framework ON framework.slug = platform.framework_slug
ON CONFLICT DO NOTHING;

WITH recommendation(framework_slug, repository_url, display_order) AS (
    VALUES
        (
            'sentence-transformers',
            'https://github.com/huggingface/sentence-transformers',
            0
        ),
        ('vllm', 'https://github.com/vllm-project/vllm', 1),
        (
            'text-embeddings-inference',
            'https://github.com/huggingface/text-embeddings-inference',
            2
        )
)
INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT task.id, framework.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = 'embedding-models'
JOIN frameworks framework ON framework.slug = recommendation.framework_slug
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

WITH recommendation(repository_url, display_order) AS (
    VALUES
        ('https://github.com/huggingface/sentence-transformers', 0),
        ('https://github.com/vllm-project/vllm', 1),
        ('https://github.com/huggingface/text-embeddings-inference', 2)
)
INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = 'embedding-models'
JOIN repositories repository ON repository.url = recommendation.repository_url
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
