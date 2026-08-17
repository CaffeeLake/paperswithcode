-- Canonicalize the 3D Tracking task slug while preserving its task id and links.
UPDATE tasks
SET slug = '3D-tracking',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = '3d-tracking';
