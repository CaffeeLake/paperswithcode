-- Add the visual/industrial image anomaly detection subtask requested in
-- huggingface/paperswithcode-feedback#17.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Image Anomaly Detection',
    'image-anomaly-detection',
    'Image anomaly detection identifies and localizes unusual or defective regions in images, typically by learning normal visual appearance from defect-free examples. It covers industrial inspection, feature-memory and reconstruction-based methods, few- and zero-shot settings, and image- and pixel-level evaluation on benchmarks such as MVTec AD and VisA.',
    'image anomaly detection, image anomaly localization, image anomaly segmentation, industrial image anomaly detection, industrial visual anomaly detection, industrial anomaly detection, industrial anomaly localization, industrial anomaly segmentation, surface anomaly detection, surface anomaly localization, zero-shot visual anomaly detection, few-shot visual anomaly detection, MVTec AD, MVTec LOCO AD, Real-IAD',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'anomaly-detection' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'anomaly-detection' LIMIT 1),
    NULL,
    '[Anomaly Detection: What Is It, Types, Use Cases, and More](https://encord.com/blog/anomaly-detection/)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
