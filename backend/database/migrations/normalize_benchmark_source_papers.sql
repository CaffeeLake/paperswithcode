-- Migration: Normalize benchmark source-paper links
-- Description:
--   Links active benchmark datasets to local paper rows when their paper_url
--   contains an arXiv ID already present in papers, then normalizes the
--   displayed source title, canonical paper URL, and introduced year.
-- Date: 2026-05-09

WITH active_benchmarks AS (
    SELECT DISTINCT dataset_id
    FROM evaluations
    WHERE dataset_id IS NOT NULL

    UNION

    SELECT DISTINCT dataset_id
    FROM task_dataset_metrics
    WHERE dataset_id IS NOT NULL
),
paper_candidates AS (
    SELECT
        d.id AS dataset_id,
        p.id AS paper_id,
        p.arxiv_id,
        p.title,
        EXTRACT(YEAR FROM p.date_published)::integer AS published_year
    FROM datasets d
    JOIN active_benchmarks ab ON ab.dataset_id = d.id
    JOIN papers p
        ON p.is_latest_version
        AND p.arxiv_id = COALESCE(
            substring(d.paper_url FROM 'arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?'),
            substring(d.paper_url FROM 'huggingface\.co/papers/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?'),
            substring(d.paper_url FROM '/(?:paper|abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?')
        )
    WHERE d.paper_url IS NOT NULL
        AND d.paper_url <> ''
),
normalized AS (
    UPDATE datasets d
    SET
        introducing_paper_id = pc.paper_id,
        introducing_paper_title = pc.title,
        paper_url = 'https://arxiv.org/abs/' || pc.arxiv_id,
        introduced_year = COALESCE(d.introduced_year, pc.published_year)
    FROM paper_candidates pc
    WHERE d.id = pc.dataset_id
        AND (
            d.introducing_paper_id IS DISTINCT FROM pc.paper_id
            OR d.introducing_paper_title IS DISTINCT FROM pc.title
            OR d.paper_url IS DISTINCT FROM ('https://arxiv.org/abs/' || pc.arxiv_id)
            OR (d.introduced_year IS NULL AND pc.published_year IS NOT NULL)
        )
    RETURNING
        d.id,
        d.slug,
        d.name,
        pc.arxiv_id,
        d.introducing_paper_id,
        d.introducing_paper_title,
        d.paper_url,
        d.introduced_year
)
SELECT
    id AS dataset_id,
    slug,
    name,
    arxiv_id,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_year
FROM normalized
ORDER BY name;
