INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'SIGGRAPH 2026',
    'siggraph-2026',
    'SIGGRAPH',
    2026,
    'https://s2026.siggraph.org/',
    '2026-07-19',
    '2026-07-23',
    'Los Angeles Convention Center',
    'Los Angeles, California, USA',
    'SIGGRAPH is the premier conference on computer graphics and interactive techniques, spanning rendering, animation, simulation, immersive experiences, AI, art, and design. Browse SIGGRAPH 2026 technical papers with code, tasks, evaluations, and Hugging Face artifacts where available.',
    NULL,
    '[SIGGRAPH 2026](https://s2026.siggraph.org/)',
    'https://huggingface.co/datasets/ai-conferences/SIGGRAPH2026'
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
