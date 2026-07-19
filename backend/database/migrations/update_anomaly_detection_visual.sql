UPDATE tasks
SET image_url = NULL,
    image_credit = '[Anomaly Detection: What Is It, Types, Use Cases, and More](https://encord.com/blog/anomaly-detection/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'anomaly-detection';
