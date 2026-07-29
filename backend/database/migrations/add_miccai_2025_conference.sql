INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'MICCAI 2025',
    'miccai-2025',
    'MICCAI',
    2025,
    'https://conferences.miccai.org/2025/en/',
    '2025-09-23',
    '2025-09-27',
    'Daejeon Convention Center',
    'Daejeon, South Korea',
    'MICCAI (International Conference on Medical Image Computing and Computer Assisted Intervention) is a leading venue for medical imaging, computer-assisted intervention, and related machine learning research. Browse accepted papers from MICCAI 2025 in Daejeon, grouped by research area and task, with code, project links, evals and Hugging Face artifacts where available.',
    NULL,
    '[MICCAI 2025](https://conferences.miccai.org/2025/en/)',
    'https://huggingface.co/datasets/ai-conferences/MICCAI2025'
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
