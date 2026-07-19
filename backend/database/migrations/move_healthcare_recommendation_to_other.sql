UPDATE tasks
SET
    area_id = (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    updated_at = CURRENT_TIMESTAMP
WHERE slug IN (
    'healthcare',
    'recommendation-systems',
    'collaborative-filtering',
    'sequential-recommendation',
    'session-based-recommendation',
    'click-through-rate-prediction',
    'learning-to-rank',
    'generative-recommendation',
    'knowledge-aware-multimodal-recommendation'
);
