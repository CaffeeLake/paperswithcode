-- Earth Observation task (Vision): satellite and aerial sensing of the planet at scale.
-- Sister of remote-sensing (technique-focused vs domain-focused taxonomy).

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Earth Observation',
    'earth-observation',
    'Earth observation (EO) applies machine learning to satellite, aerial, and drone sensor data for environmental monitoring, land cover mapping, disaster response, agriculture, and climate science. Methods span multispectral and hyperspectral classification, change detection, segmentation, and geospatial foundation models trained across resolutions and sensor modalities. Closely related to [Remote Sensing](/tasks/remote-sensing) for sensor-centric analysis and [Image Segmentation](/tasks/image-segmentation) for pixel-level land mapping.',
    'earth observation, satellite earth observation, multispectral earth observation, hyperspectral earth observation, foundation model for earth observation, geospatial foundation model for earth observation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[UniverSat: Resolution- and Modality-Agnostic Transformers for Earth Observation](/paper/2606.23503)',
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

-- Sister tasks: Earth Observation <-> Remote Sensing (bidirectional).
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'remote-sensing'
WHERE t.slug = 'earth-observation'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'earth-observation'
WHERE t.slug = 'remote-sensing'
ON CONFLICT DO NOTHING;

-- UniverSat introducing paper on the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'earth-observation'
WHERE p.arxiv_id = '2606.23503'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';
