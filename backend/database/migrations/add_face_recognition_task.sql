-- Face recognition task (Vision): 1:N identification and open-set matching.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Face Recognition',
    'face-recognition',
    'Face recognition identifies or verifies a person from a face image, typically by embedding faces into a metric space for 1:N gallery search or open-set matching. Modern pipelines train on large-scale identity-labeled data (e.g. MS1MV2, WebFace42M) with margin-based losses and evaluate on identification benchmarks such as MegaFace and IJB, complementing pairwise [Face Verification](/tasks/face-verification).',
    'face recognition, face identification, 1:N face recognition, closed-set face recognition, open-set face recognition, megaface, IJB, MFR, masked face recognition, unconstrained face recognition, face embedding, deep face recognition, gallery search',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[ArcFace: Additive Angular Margin Loss for Deep Face Recognition](/paper/1801.07698)',
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

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('face-verification', 0)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'face-recognition'
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'face-recognition'
WHERE p.arxiv_id = '2501.13420'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
