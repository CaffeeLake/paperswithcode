-- Link Vintage Data explainer as canonical source for mid-training (no introducing paper).
UPDATE methods
SET
    source_url = 'https://vintagedata.org/blog/posts/what-is-mid-training',
    source_title = 'What''s the deal with mid-training?',
    introduced_year = 2025,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'mid-training';
