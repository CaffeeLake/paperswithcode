INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'ACL 2026',
    'acl-2026',
    'ACL',
    2026,
    'https://2026.aclweb.org/',
    '2026-07-02',
    '2026-07-07',
    'Grand Hyatt Manchester San Diego',
    'San Diego, California, USA',
    'ACL (Annual Meeting of the Association for Computational Linguistics) is a flagship venue for natural language processing and computational linguistics. Browse accepted papers from ACL 2026 in San Diego, grouped by research area and task, with code, project links, evals and Hugging Face artifacts where available.',
    NULL,
    '[ACL 2026](https://2026.aclweb.org/)',
    'https://huggingface.co/datasets/ai-conferences/ACL2026'
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
