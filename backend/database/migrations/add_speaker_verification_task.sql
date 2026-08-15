-- Speaker verification task and VoxCeleb1-O EER leaderboard.
--
-- VoxCeleb1 is also used for closed-set speaker identification under the
-- Audio Classification task.  This task-specific association represents the
-- open-set verification protocol: cleaned VoxCeleb1-O trials ranked by EER.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Speaker Verification',
    'speaker-verification',
    'Speaker verification determines whether two speech recordings belong to the same person, typically by comparing learned speaker embeddings in an open-set setting. Unlike closed-set speaker identification under [Audio Classification](/tasks/audio-classification), verification accepts or rejects a claimed identity and is commonly evaluated using equal error rate (EER) and minimum detection cost.',
    'speaker verification, speaker authentication, voice verification, text-independent speaker verification, text dependent speaker verification, speaker embedding, speaker embeddings, speaker recognition',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[ERes2NetV2: Boosting Short-Duration Speaker Verification Performance with Computational Efficiency](/paper/2406.02167)',
    'https://github.com/modelscope/3D-Speaker'
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

UPDATE datasets
SET description = 'VoxCeleb1 contains over 100,000 utterances for 1,251 celebrities, extracted from videos uploaded to YouTube. It supports closed-set speaker identification (Accuracy under Audio Classification) and open-set speaker verification using the cleaned VoxCeleb1-O trial list (EER under Speaker Verification).',
    warning = 'The Speaker Verification leaderboard uses cleaned VoxCeleb1-O trials and EER. The Audio Classification leaderboard uses speaker-identification Accuracy; scores from the two tasks are not comparable.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'voxceleb1';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, false
FROM tasks t
JOIN datasets d ON d.slug = 'voxceleb1'
WHERE t.slug = 'speaker-verification'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'voxceleb1'
JOIN metrics m ON m.name = 'EER'
WHERE t.slug = 'speaker-verification'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'speaker-verification'
WHERE p.arxiv_id IN (
    '1706.08612',
    '2005.07143',
    '2303.00332',
    '2305.12838',
    '2401.08342',
    '2401.17230',
    '2403.19971',
    '2406.02167',
    '2407.18223'
)
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'audio-classification'
WHERE t.slug = 'speaker-verification'
ON CONFLICT DO NOTHING;
