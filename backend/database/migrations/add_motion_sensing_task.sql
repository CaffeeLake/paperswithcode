INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    is_visible,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'Motion Sensing',
    'motion-sensing',
    'Motion sensing learns representations and predictions from wearable and ambient inertial signals such as accelerometers, gyroscopes, and IMUs. It covers sensor-based human activity recognition, gait and mobility analysis, and health-related behavior modeling across devices, body placements, sampling rates, and deployment conditions.',
    'wearable motion sensing, wearable sensing, wearable inertial sensing, wearable inertial sensor, wearable inertial sensors, wearable IMU, wearable IMUs, wearable accelerometer, wearable accelerometers, wearable gyroscope, wearable gyroscopes, sensor-based human activity recognition, wearable human activity recognition, activity recognition from wearable sensors, activity recognition using wearable sensors, wearable motion foundation model, wearable motion foundation models, motion representation learning for wearables, wearable sensor representation learning, wearable time series, wearable sensor data, wearable gait detection, wearable freezing of gait detection',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Inertia-1: An Open Exploration of Wearable Motion Foundation Models](/paper/2607.06617)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
