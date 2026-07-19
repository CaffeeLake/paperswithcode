-- Drop ambiguous keywords from Camera Pose Estimation. Bare "camera pose" also
-- matches papers that consume known poses for rendering or generation, while ATE
-- and RPE collide with unrelated metrics, positional encodings, and error terms.

UPDATE tasks
SET keywords = 'camera pose estimation, camera localization, camera trajectory estimation, camera motion estimation, relative camera pose, absolute camera pose, visual odometry',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'camera-pose-estimation';
