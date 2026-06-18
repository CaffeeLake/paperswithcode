-- Broaden world-models coverage beyond generative/video phrasing so robot and
-- interaction-centric world models (e.g. trace-space dynamics) auto-tag correctly.

UPDATE tasks
SET keywords = 'world model, world models, generative world model, world action model, video world model, robot world model, embodied world model',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'world-models';
