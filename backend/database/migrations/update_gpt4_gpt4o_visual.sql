UPDATE methods
SET
    image_url = '/api/thumbnails/2303_08774_v5.jpg?fit=fit3',
    image_credit = '[GPT-4 Technical Report](/paper/2303.08774)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gpt-4';

UPDATE methods
SET
    source_paper_id = (
        SELECT id FROM papers WHERE id = 97934 LIMIT 1
    ),
    source_url = NULL,
    source_title = 'Hello GPT-4o',
    image_url = '/api/thumbnails/custom/external_97934.jpg?fit=fit2',
    image_credit = '[Hello GPT-4o](/paper/97934)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gpt-4o';

INSERT INTO paper_methods (paper_id, method_id)
SELECT 97934, id
FROM methods
WHERE slug = 'gpt-4o'
ON CONFLICT (paper_id, method_id) DO NOTHING;
