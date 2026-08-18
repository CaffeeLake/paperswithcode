-- Spoken language identification task taxonomy.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Spoken Language Identification',
    'spoken-language-identification',
    'Spoken language identification determines which language is present in an audio recording without requiring a transcript. Systems map speech segments to language labels and are commonly used to route multilingual audio to the appropriate [Automatic Speech Recognition](/tasks/automatic-speech-recognition) or speech-processing model.',
    'spoken language identification, speech language identification, spoken language recognition, speech language recognition, audio language identification, audio language recognition, language identification from speech, language identification from audio, speech LID',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[VoxLingua107: a Dataset for Spoken Language Recognition](/paper/2011.12998)',
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
SELECT t.id, s.id, v.display_order
FROM tasks t
CROSS JOIN (VALUES
    ('audio-classification', 0),
    ('automatic-speech-recognition', 1)
) AS v(slug, display_order)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'spoken-language-identification'
ON CONFLICT DO NOTHING;
