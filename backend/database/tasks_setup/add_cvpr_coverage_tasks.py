#!/usr/bin/env python3
"""Add CVPR-oriented coverage tasks and expand Omni models keywords."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.api import TaskCreateRequest
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GENERAL_AREA_ID = 3
VISION_AREA_ID = 1
VIDEO_AREA_ID = 9

OMNI_MODELS_KEYWORDS = (
    "omni model, omni models, omni-modal, omnimodal, any-to-any model, "
    "interleaved multimodal, omni understanding"
)

TASKS = [
    {
        "slug": "autonomous-driving",
        "name": "Autonomous Driving",
        "area_id": GENERAL_AREA_ID,
        "description": (
            "Autonomous driving research covers perception, planning, and control for "
            "self-driving vehicles, including bird's-eye-view (BEV) perception, "
            "occupancy prediction, end-to-end driving, and ADAS."
        ),
        "keywords": (
            "self-driving, self driving, end-to-end driving, ADAS, BEV perception, "
            "driving scene understanding, autonomous driving system, self-driving car, "
            "self-driving vehicle, occupancy prediction for autonomous driving"
        ),
    },
    {
        "slug": "anomaly-detection",
        "name": "Anomaly Detection",
        "area_id": GENERAL_AREA_ID,
        "description": (
            "Anomaly and out-of-distribution (OOD) detection identifies unusual, "
            "novel, or defective inputs in images, video, and other sensor data."
        ),
        "keywords": (
            "industrial anomaly, out-of-distribution detection, OOD detection, "
            "unsupervised anomaly detection, anomaly localization, "
            "zero-shot anomaly detection, video anomaly detection, anomaly segmentation, "
            "image anomaly detection"
        ),
    },
    {
        "slug": "remote-sensing",
        "name": "Remote Sensing",
        "area_id": GENERAL_AREA_ID,
        "description": (
            "Remote sensing analyzes satellite, aerial, and drone imagery for "
            "land cover, environmental monitoring, geospatial understanding, and "
            "earth observation."
        ),
        "keywords": "remote sensing, satellite imagery, aerial imagery, drone imagery",
    },
    {
        "slug": "deepfake-and-forensics",
        "name": "Deepfake and Forensics",
        "area_id": GENERAL_AREA_ID,
        "description": (
            "Deepfake detection and media forensics identify synthetic, manipulated, "
            "or spoofed visual and audiovisual content, including anti-spoofing and "
            "security-oriented authenticity verification."
        ),
        "keywords": (
            "deepfake detection, media forensics, face forensics, anti-spoofing, "
            "spoofing detection, synthetic media detection, face anti-spoof, "
            "face forgery detection, video forgery detection"
        ),
    },
    {
        "slug": "object-tracking",
        "name": "Object Tracking",
        "area_id": VIDEO_AREA_ID,
        "description": (
            "Object tracking follows one or more targets across video frames, "
            "including single-object tracking, multi-object tracking (MOT), and "
            "tracking-by-detection pipelines."
        ),
        "keywords": (
            "multi-object tracking, MOT, single object tracking, tracking-by-detection, "
            "multi object track, visual object tracking"
        ),
    },
    {
        "slug": "image-restoration",
        "name": "Image Restoration",
        "area_id": VISION_AREA_ID,
        "description": (
            "Image restoration recovers clean images from degraded inputs such as "
            "noise, blur, rain, haze, or missing regions via denoising, deblurring, "
            "inpainting, and related enhancement methods."
        ),
        "keywords": (
            "image restoration, image denoising, image deblurring, deraining, dehazing, "
            "blind image restoration, rain removal, haze removal"
        ),
    },
    {
        "slug": "medical-imaging",
        "name": "Medical Imaging",
        "area_id": VISION_AREA_ID,
        "description": (
            "Medical imaging applies computer vision to clinical and biomedical "
            "images, including radiology, pathology, fundus imaging, ultrasound, "
            "and diagnostic analysis."
        ),
        "keywords": (
            "medical imaging, digital pathology, computational pathology, mammography, "
            "histopathology, clinical imaging, retinal imaging, fundus, ultrasound imaging, "
            "whole slide imaging, medical image segmentation, medical image analysis"
        ),
    },
    {
        "slug": "optical-flow",
        "name": "Optical Flow",
        "area_id": VISION_AREA_ID,
        "description": (
            "Optical flow estimates dense or sparse motion fields between consecutive "
            "frames or views, supporting video analysis, action understanding, and "
            "geometric reasoning."
        ),
        "keywords": (
            "optical flow estimation, dense optical flow, optical flow network, "
            "optical flow prediction, optical flow model"
        ),
    },
    {
        "slug": "stereo-matching",
        "name": "Stereo Matching",
        "area_id": VISION_AREA_ID,
        "description": (
            "Stereo matching estimates disparity or depth from rectified image pairs, "
            "supporting 3D reconstruction and geometric vision pipelines."
        ),
        "keywords": (
            "stereo matching, stereo disparity, disparity estimation, depth from stereo"
        ),
    },
    {
        "slug": "slam-and-localization",
        "name": "SLAM and Localization",
        "area_id": VISION_AREA_ID,
        "description": (
            "SLAM and visual localization estimate camera pose and build maps from "
            "visual observations, including visual odometry and structure-from-motion."
        ),
        "keywords": (
            "simultaneous localization and mapping, visual odometry, visual SLAM, "
            "RGB-D SLAM, LiDAR SLAM, monocular SLAM, Gaussian Splatting SLAM"
        ),
    },
]


def ensure_task(session, spec: dict) -> int:
    row = session.execute(
        text("SELECT id, area_id, description, keywords FROM tasks WHERE slug = :slug"),
        {"slug": spec["slug"]},
    ).first()
    if row:
        task_id = int(row[0])
        updates: dict[str, object] = {"id": task_id}
        changed_fields: list[str] = []

        for field in ("area_id", "description", "keywords"):
            if row[field] != spec[field]:
                updates[field] = spec[field]
                changed_fields.append(field)

        if changed_fields:
            set_clause = ", ".join(f"{field} = :{field}" for field in changed_fields)
            session.execute(
                text(f"UPDATE tasks SET {set_clause} WHERE id = :id"),
                updates,
            )
            logger.info(
                "Updated %s (id=%s): %s",
                spec["name"],
                task_id,
                ", ".join(changed_fields),
            )
        else:
            logger.info("Task already exists: %s (id=%s)", spec["name"], task_id)
        return task_id

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=spec["name"],
            description=spec["description"],
            keywords=spec["keywords"],
            area_id=spec["area_id"],
        )
    )
    logger.info("Created task: %s (id=%s)", spec["name"], task.id)
    return int(task.id)


def update_omni_models_keywords(session) -> None:
    row = session.execute(
        text("SELECT id, keywords FROM tasks WHERE slug = 'omni-models'")
    ).first()
    if not row:
        raise RuntimeError("Omni models task not found")

    task_id, current_keywords = int(row[0]), row[1] or ""
    if current_keywords == OMNI_MODELS_KEYWORDS:
        logger.info("Omni models keywords already up to date (id=%s)", task_id)
        return

    session.execute(
        text("UPDATE tasks SET keywords = :keywords WHERE id = :id"),
        {"keywords": OMNI_MODELS_KEYWORDS, "id": task_id},
    )
    logger.info("Updated Omni models keywords (id=%s)", task_id)


def main() -> None:
    session = db_manager.session_local()
    try:
        for spec in TASKS:
            ensure_task(session, spec)
        update_omni_models_keywords(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
