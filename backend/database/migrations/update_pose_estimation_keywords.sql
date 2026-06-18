-- Drop bare "keypoints" from pose-estimation: it false-positives on robotics,
-- tracking, and world-model papers that mention interaction/object keypoints.
-- Prefer human/skeleton-specific phrases plus existing pose terms.

UPDATE tasks
SET keywords = 'pose estimation, human pose estimation, keypoint detection, human keypoints, skeleton keypoints, body joints',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'pose-estimation';
