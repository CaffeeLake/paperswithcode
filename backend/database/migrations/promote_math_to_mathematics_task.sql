UPDATE tasks
SET name = 'Mathematics',
    area_id = (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    parent_id = NULL,
    level = 0,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'math';
