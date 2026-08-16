INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Emotion Recognition',
    'emotion-recognition',
    'Emotion Recognition identifies affective states from signals such as facial expressions, speech and audio, text and conversational context, body language, and physiological measurements including EEG. Systems may predict discrete emotion categories or continuous dimensions such as valence and arousal, and may combine multiple modalities for more robust human-computer interaction.',
    'emotion recognition, emotion classification, emotion detection, affect recognition, affect classification, affective state recognition, facial emotion recognition, facial expression recognition, speech emotion recognition, audio emotion recognition, multimodal emotion recognition, EEG emotion recognition, emotion recognition in conversation, FER, SER',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    'Generated concept image',
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
