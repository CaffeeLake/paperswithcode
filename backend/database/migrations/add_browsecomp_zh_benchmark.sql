-- BrowseComp-ZH: a Chinese deep-research benchmark introduced by arXiv 2504.19314.

BEGIN;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    hf_url, introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, modalities
)
SELECT
    'BrowseComp-ZH',
    'BrowseComp-ZH: Benchmarking Web Browsing Agents in Chinese',
    'browsecomp-zh',
    'BrowseComp-ZH is a benchmark of 289 challenging Chinese-language questions across 11 domains. Questions require multi-hop web browsing, retrieval, reasoning, and evidence synthesis, and are designed so that answers are difficult to obtain from a single search result.',
    '289 multi-hop Chinese web-research questions across 11 domains.',
    'https://github.com/PALIN2018/BrowseComp-ZH',
    'https://github.com/PALIN2018/BrowseComp-ZH',
    'https://huggingface.co/datasets/PALIN2018/BrowseComp-ZH',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2504.19314',
    DATE '2025-04-27',
    2025,
    '["Text", "Web"]'::jsonb
FROM papers p
WHERE p.arxiv_id = '2504.19314'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    hf_url = EXCLUDED.hf_url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug = 'browsecomp-zh'
WHERE t.slug = 'deep-research-agents'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'browsecomp-zh'
CROSS JOIN metrics m
WHERE t.slug = 'deep-research-agents'
  AND m.name = 'Accuracy'
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'deep-research-agents'
WHERE p.arxiv_id = '2504.19314'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
