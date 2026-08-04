INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'COLM 2026',
    'colm-2026',
    'COLM',
    2026,
    'https://colmweb.org/',
    '2026-10-06',
    '2026-10-09',
    'Hilton San Francisco Union Square',
    'San Francisco, California, USA',
    'COLM (Conference on Language Modeling) is an academic venue focused on understanding, improving, and critiquing language models across disciplines. Browse accepted COLM 2026 papers with code, tasks, evaluations, and Hugging Face artifacts where available.',
    NULL,
    '[COLM 2026](https://colmweb.org/)',
    'https://huggingface.co/datasets/ai-conferences/COLM2026'
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
