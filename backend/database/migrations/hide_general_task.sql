-- Hide the legacy "General" task from user-facing pickers.
-- "General" is a research area, not a taggable task.

UPDATE tasks
SET is_visible = FALSE
WHERE slug = 'general';
