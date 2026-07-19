-- Link ASR, text-to-speech, and audio-classification as mutual sister tasks.
-- Speech diarization is not a task yet; add it to this group when created.

BEGIN;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id,
    CASE s.slug
        WHEN 'audio-classification' THEN 0
        WHEN 'automatic-speech-recognition' THEN 1
        WHEN 'text-to-speech' THEN 2
    END
FROM tasks t
JOIN tasks s ON s.slug IN (
    'automatic-speech-recognition',
    'text-to-speech',
    'audio-classification'
) AND s.id <> t.id
WHERE t.slug IN (
    'automatic-speech-recognition',
    'text-to-speech',
    'audio-classification'
)
ON CONFLICT DO NOTHING;

COMMIT;
