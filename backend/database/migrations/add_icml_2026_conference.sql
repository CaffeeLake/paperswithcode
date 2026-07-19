INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'ICML 2026',
    'icml-2026',
    'ICML',
    2026,
    'https://icml.cc/Conferences/2026',
    '2026-07-06',
    '2026-07-11',
    'COEX Convention & Exhibition Center',
    'Seoul, South Korea',
    'ICML (International Conference on Machine Learning) is a leading venue for machine learning research. Browse accepted papers from ICML 2026 in Seoul, grouped by research area and task, with code, project links, evals and Hugging Face artifacts where available.',
    NULL,
    '[ICML 2026](https://icml.cc/Conferences/2026)',
    'https://huggingface.co/datasets/ai-conferences/ICML2026'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    short_name = EXCLUDED.short_name,
    year = EXCLUDED.year,
    url = EXCLUDED.url,
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date,
    venue = EXCLUDED.venue,
    location = EXCLUDED.location,
    description = EXCLUDED.description,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    hf_url = EXCLUDED.hf_url,
    updated_at = CURRENT_TIMESTAMP;
