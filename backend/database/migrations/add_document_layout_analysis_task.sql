-- Document layout analysis task (Vision): detect and segment layout elements in document pages.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Document Layout Analysis',
    'document-layout-analysis',
    'Document layout analysis localizes and classifies structural page elements—such as titles, paragraphs, lists, tables, and figures—in scanned or born-digital documents. It is a core step for [Document Understanding](/tasks/document-understanding) pipelines and is often evaluated with COCO-style detection metrics (mAP) on benchmarks like DocLayNet and PubLayNet.',
    'document layout analysis, document layout, layout detection, layout segmentation, DLA, document parsing, page segmentation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[DocLayNet: A Large Human-Annotated Dataset for Document-Layout Analysis](/paper/2206.01062)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
