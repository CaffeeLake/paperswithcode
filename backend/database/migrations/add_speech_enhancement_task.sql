-- Speech enhancement task (Audio): denoise, restore, separate, and extract clean speech.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Speech Enhancement',
    'speech-enhancement',
    'Speech enhancement improves degraded speech by suppressing noise, reverberation, and interference while preserving intelligibility and naturalness. It covers speech restoration, target speaker extraction, speech separation, and noise suppression, complementing [Automatic Speech Recognition](/tasks/automatic-speech-recognition) and [Audio understanding](/tasks/audio-understanding).',
    'speech enhancement, SE, speech restoration, speech denoising, noise suppression, dereverberation, target speaker extraction, TSE, speech separation, voice enhancement, noisy speech enhancement, single-channel speech enhancement, multi-channel speech enhancement, DNS challenge',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[UniSE: A Unified Framework for Decoder-only Autoregressive LM-based Speech Enhancement](/paper/2510.20441)',
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

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'speech-enhancement'
WHERE p.arxiv_id = '2510.20441'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
