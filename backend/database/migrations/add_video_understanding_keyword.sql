-- Ensure papers that explicitly describe video understanding are tagged with
-- the Video Understanding task, including papers whose titles use the task
-- name directly rather than the existing video-language-model variants.
UPDATE tasks
SET keywords = CASE
    WHEN keywords IS NULL OR keywords = '' THEN 'video understanding'
    WHEN keywords ILIKE '%video understanding%' THEN keywords
    ELSE keywords || ', video understanding'
END,
updated_at = CURRENT_TIMESTAMP
WHERE slug = 'video-understanding';
