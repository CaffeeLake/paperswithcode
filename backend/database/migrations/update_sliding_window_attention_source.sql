UPDATE methods
SET source_paper_id = (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2004.05150'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    source_url = NULL,
    source_title = 'Longformer: The Long-Document Transformer',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'sliding-window-attention';

INSERT INTO paper_methods (paper_id, method_id)
SELECT m.source_paper_id, m.id
FROM methods m
WHERE m.slug = 'sliding-window-attention'
  AND m.source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
