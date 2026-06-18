-- Audio generation task (Audio): synthesize music, speech, and general sounds.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Audio Generation',
    'audio-generation',
    'Audio generation synthesizes music, speech, sound effects, or general audio from prompts, conditioning signals, or other media. It covers text-to-audio, text-to-music, audio continuation, and controllable sound synthesis, complementing [Audio understanding](/tasks/audio-understanding) and [Text-to-speech](/tasks/text-to-speech).',
    'audio generation, audio synthesis, generative audio, text-to-audio, text to audio, text-to-music, text to music, music generation, sound generation, sound effect generation, audio diffusion, latent audio diffusion, audio continuation, controllable audio generation, waveform generation, Stable Audio',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    'Generated locally for the Audio Generation task',
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
JOIN tasks t ON t.slug = 'audio-generation'
WHERE p.arxiv_id = '2605.17991'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
