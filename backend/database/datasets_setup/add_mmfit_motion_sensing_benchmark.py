#!/usr/bin/env python3
"""Add the canonical MM-Fit cross-subject multimodal benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "mm-fit"
SOURCE_URL = "https://doi.org/10.1145/3432701"
SOURCE_TITLE = (
    "MM-Fit: Multimodal Deep Learning for Automatic Exercise Logging "
    "across Sensing Devices"
)
DATA_URL = "https://mmfit.github.io/"
CODE_URL = "https://github.com/KDMStromback/mm-fit"
HERO_URL = "https://mmfit.github.io/images/architecture.png"


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces MM-Fit, a time-synchronised multimodal dataset "
                    "of full-body workouts, and establishes baselines for "
                    "activity segmentation, exercise recognition, and "
                    "repetition counting across wearable inertial sensors and "
                    "3D human pose."
                ),
                authors=["David Strömbäck", "Sangxia Huang", "Valentin Radu"],
                date_published=date(2020, 12, 1),
                thumbnail_url=HERO_URL,
                github_repository_urls=[CODE_URL],
            )
        )
        paper_id = source.paper.id
        native_paper_url = f"https://paperswithcode.co/paper/{paper_id}"

        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).scalar_one()
        metric_id = db.execute(
            text(
                """
                SELECT id
                FROM metrics
                WHERE name = 'Accuracy'
                  AND direction = 'higher_is_better'
                  AND scale = '0-100'
                """
            )
        ).scalar_one()

        dataset_id = db.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    url, homepage, image_url, thumbnail_url,
                    verified_image_url, introducing_paper_id,
                    introducing_paper_title, paper_url, introduced_date,
                    introduced_year, modalities, split_name, warning, pwc_url
                )
                VALUES (
                    'MM-Fit (Cross-Subject, Full Multimodal)',
                    :slug,
                    'MM-Fit Multimodal Exercise Dataset',
                    'MM-Fit contains 21 single-person workout sessions from '
                    '10 participants, totalling 809 minutes, 616 exercise sets, '
                    'and 6,160 repetitions. Its 11 recognition labels are '
                    'squats, lunges, bicep curls, sit-ups, push-ups, triceps '
                    'extensions, dumbbell rows, jumping jacks, dumbbell shoulder '
                    'press, lateral shoulder raises, and non-activity. The '
                    'canonical cross-subject benchmark fuses nine synchronized '
                    'streams: triaxial accelerometer and gyroscope from each '
                    'wristwatch, the right-pocket phone, and the left earbud, '
                    'plus monocular 3D pose from one camera. Inertial streams '
                    'are resampled to 50 Hz and 3D pose remains at 30 Hz.',
                    'Eleven-class exercise recognition from wearable inertial '
                    'sensors and 3D pose on the official unseen-participant split.',
                    :data_url,
                    :code_url,
                    :hero_url,
                    :hero_url,
                    :hero_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2020-12-01',
                    2020,
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Gyroscope", "3D Human Pose", "Multimodal"]'::jsonb,
                    'Cross-subject: train 01-04,06-08,16-18; val 14,15,19; '
                    'unseen test 00,05,12,13,20',
                    'Protocol: use all nine streams in the introducing paper''s '
                    'full multimodal model: 3D pose from one RGB-D camera plus '
                    'triaxial accelerometer and gyroscope from the left and right '
                    'watches, right-pocket Samsung S7 phone, and left earbud. '
                    'Use the 11 labels listed in the description. Apply the '
                    'official fixed workout allocation: training IDs 01, 02, '
                    '03, 04, 06, 07, 08, 16, 17, 18; validation IDs 14, 15, 19; '
                    'and previously unseen-participant test IDs 00, 05, 12, 13, '
                    '20. Resample inertial inputs to 50 Hz, retain pose at 30 Hz, '
                    'form 5-second windows (250 inertial samples and 150 pose '
                    'frames), assign the majority label, and evaluate sequential '
                    'test windows at a 0.2-second stride. Report micro Accuracy '
                    'over the unseen-participant test windows as a percentage '
                    'from 0 to 100. Exclude the seen-subject test IDs 09/10/11, '
                    'random window/session splits, leave-one-subject-out or other '
                    'subject allocations, and altered window lengths, strides, '
                    'sampling rates, label sets, or score scales. Also exclude '
                    'single-device or modality-subset results, zeroing-out '
                    'training results, raw RGB/depth or 2D-pose inputs, the second '
                    'camera, Huawei phone, magnetometer, or heart-rate variants, '
                    'and repetition-counting metrics; each requires a separate '
                    'leaderboard.',
                    'https://paperswithcode.com/dataset/mm-fit'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    url = EXCLUDED.url,
                    homepage = EXCLUDED.homepage,
                    image_url = EXCLUDED.image_url,
                    thumbnail_url = EXCLUDED.thumbnail_url,
                    verified_image_url = EXCLUDED.verified_image_url,
                    introducing_paper_id = EXCLUDED.introducing_paper_id,
                    introducing_paper_title = EXCLUDED.introducing_paper_title,
                    paper_url = EXCLUDED.paper_url,
                    introduced_date = EXCLUDED.introduced_date,
                    introduced_year = EXCLUDED.introduced_year,
                    modalities = EXCLUDED.modalities,
                    split_name = EXCLUDED.split_name,
                    warning = EXCLUDED.warning,
                    pwc_url = EXCLUDED.pwc_url,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
            ),
            {
                "slug": DATASET_SLUG,
                "data_url": DATA_URL,
                "code_url": CODE_URL,
                "hero_url": HERO_URL,
                "paper_id": paper_id,
                "paper_title": SOURCE_TITLE,
                "paper_url": native_paper_url,
            },
        ).scalar_one()

        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper_id, "task_id": task_id},
        )
        db.execute(
            text(
                """
                INSERT INTO task_datasets (
                    task_id, dataset_id, featured_rank, supports_harness
                )
                VALUES (:task_id, :dataset_id, NULL, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    featured_rank = NULL,
                    supports_harness = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id},
        )
        db.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "task_id": task_id,
                "dataset_id": dataset_id,
                "metric_id": metric_id,
            },
        )
        db.commit()
        print(
            {
                "dataset_id": dataset_id,
                "dataset_slug": DATASET_SLUG,
                "task_id": task_id,
                "metric_id": metric_id,
                "source_paper_id": paper_id,
                "source_paper_url": native_paper_url,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
