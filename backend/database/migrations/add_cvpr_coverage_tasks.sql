-- Add CVPR-oriented coverage tasks and expand Omni models keywords.

INSERT INTO tasks (name, slug, description, keywords, area_id, level, is_visible)
VALUES
    (
        'Autonomous Driving',
        'autonomous-driving',
        'Autonomous driving research covers perception, planning, and control for self-driving vehicles, including bird''s-eye-view (BEV) perception, occupancy prediction, end-to-end driving, and ADAS.',
        'self-driving, self driving, end-to-end driving, ADAS, BEV perception, driving scene understanding, autonomous driving system, self-driving car, self-driving vehicle, occupancy prediction for autonomous driving',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        0,
        true
    ),
    (
        'Anomaly Detection',
        'anomaly-detection',
        'Anomaly and out-of-distribution (OOD) detection identifies unusual, novel, or defective inputs in images, video, and other sensor data.',
        'industrial anomaly, out-of-distribution detection, OOD detection, unsupervised anomaly detection, anomaly localization, zero-shot anomaly detection, video anomaly detection, anomaly segmentation, image anomaly detection',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        0,
        true
    ),
    (
        'Remote Sensing',
        'remote-sensing',
        'Remote sensing analyzes satellite, aerial, and drone imagery for land cover, environmental monitoring, geospatial understanding, and earth observation.',
        'remote sensing, satellite imagery, aerial imagery, drone imagery',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        0,
        true
    ),
    (
        'Deepfake and Forensics',
        'deepfake-and-forensics',
        'Deepfake detection and media forensics identify synthetic, manipulated, or spoofed visual and audiovisual content, including anti-spoofing and security-oriented authenticity verification.',
        'deepfake detection, media forensics, face forensics, anti-spoofing, spoofing detection, synthetic media detection, face anti-spoof, face forgery detection, video forgery detection',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        0,
        true
    ),
    (
        'Object Tracking',
        'object-tracking',
        'Object tracking follows one or more targets across video frames, including single-object tracking, multi-object tracking (MOT), and tracking-by-detection pipelines.',
        'multi-object tracking, MOT, single object tracking, tracking-by-detection, multi object track, visual object tracking',
        (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
        0,
        true
    ),
    (
        'Image Restoration',
        'image-restoration',
        'Image restoration recovers clean images from degraded inputs such as noise, blur, rain, haze, or missing regions via denoising, deblurring, inpainting, and related enhancement methods.',
        'image restoration, image denoising, image deblurring, deraining, dehazing, blind image restoration, rain removal, haze removal',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        0,
        true
    ),
    (
        'Medical Imaging',
        'medical-imaging',
        'Medical imaging applies computer vision to clinical and biomedical images, including radiology, pathology, fundus imaging, ultrasound, and diagnostic analysis.',
        'medical imaging, digital pathology, computational pathology, mammography, histopathology, clinical imaging, retinal imaging, fundus, ultrasound imaging, whole slide imaging, medical image segmentation, medical image analysis',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        0,
        true
    ),
    (
        'Optical Flow',
        'optical-flow',
        'Optical flow estimates dense or sparse motion fields between consecutive frames or views, supporting video analysis, action understanding, and geometric reasoning.',
        'optical flow estimation, dense optical flow, optical flow network, optical flow prediction, optical flow model',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        0,
        true
    ),
    (
        'Stereo Matching',
        'stereo-matching',
        'Stereo matching estimates disparity or depth from rectified image pairs, supporting 3D reconstruction and geometric vision pipelines.',
        'stereo matching, stereo disparity, disparity estimation, depth from stereo',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        0,
        true
    )
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    is_visible = EXCLUDED.is_visible,
    updated_at = NOW();

UPDATE tasks
SET keywords = 'omni model, omni models, omni-modal, omnimodal, any-to-any model, interleaved multimodal, omni understanding',
    updated_at = NOW()
WHERE slug = 'omni-models';
