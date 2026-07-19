#!/usr/bin/env python3
"""Add the canonical OdayFoG three-IMU LOSO benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "odayfog"
SOURCE_URL = "https://doi.org/10.1186/s12984-022-00992-x"
SOURCE_TITLE = (
    "Assessing inertial measurement unit locations for freezing of gait "
    "detection and patient preference"
)
REPOSITORY_URL = "https://github.com/stanfordnmbl/imu-fog-detection"
THUMBNAIL_URL = (
    "https://raw.githubusercontent.com/stanfordnmbl/imu-fog-detection/"
    "main/figures/classification_metrics.png"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Compares wearable inertial-measurement-unit locations for "
                    "detecting freezing of gait in people with Parkinson's "
                    "disease, using convolutional neural networks and "
                    "leave-one-subject-out validation."
                ),
                authors=[
                    "Johanna O’Day",
                    "Marissa Lee",
                    "Kirsten Seagers",
                    "Shannon Hoffman",
                    "Ava Jih-Schiff",
                    "Łukasz Kidziński",
                    "Scott Delp",
                    "Helen Bronte-Stewart",
                ],
                date_published=date(2022, 2, 13),
                thumbnail_url=THUMBNAIL_URL,
                github_repository_urls=[REPOSITORY_URL],
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
                WHERE name = 'AUROC (0-1)'
                  AND direction = 'higher_is_better'
                  AND scale = '0-1'
                """
            )
        ).scalar_one()

        dataset_id = db.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    url, homepage, introducing_paper_id,
                    introducing_paper_title, paper_url, introduced_date,
                    introduced_year, modalities, split_name, warning, pwc_url
                )
                VALUES (
                    'OdayFoG (3-IMU LOSO)',
                    :slug,
                    'OdayFoG Freezing of Gait Dataset',
                    'Freezing-of-gait detection data from seven people with '
                    'Parkinson''s disease completing 60 turning-and-barrier '
                    'walks while off medication and deep-brain stimulation. '
                    'The canonical leaderboard uses triaxial accelerometer and '
                    'gyroscope signals from the lumbar L5 sensor and bilateral '
                    'ankle sensors, downsampled from 128 Hz to 64 Hz. Signals '
                    'are standardized per 2-second window, windows overlap by '
                    '50% (64-sample/1-second stride), and the majority expert '
                    'video label determines freezing versus non-freezing. '
                    'Evaluation is seven-fold leave-one-subject-out cross-validation.',
                    'Binary freezing-of-gait detection from lumbar and bilateral '
                    'ankle IMUs with seven-subject LOSO evaluation.',
                    :repository_url,
                    :repository_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2022-02-13',
                    2022,
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Gyroscope", "Inertial Measurement Unit"]'::jsonb,
                    '7-subject LOSO; lumbar + bilateral ankles; 2 s/50% overlap',
                    'Only window-level AUROC on held-out subjects belongs here. '
                    'Use the seven-participant six-IMU cohort, retaining lumbar '
                    'L5 and both ankle sensors, 64 Hz resampling, 2-second '
                    'windows, 50% overlap, per-window standardization, and '
                    'majority video labels. Exclude the four-subject 11-IMU '
                    'subset, single-sensor and other sensor-set ablations, '
                    'random-window or patient-specific splits, gait-initiation '
                    'episodes, on-medication/DBS or assistive-device cohorts, '
                    'different windows or label rules, event-level metrics, '
                    'thresholded metrics, and percentage-scaled AUROC.',
                    'https://paperswithcode.com/dataset/odayfog'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    url = EXCLUDED.url,
                    homepage = EXCLUDED.homepage,
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
                "repository_url": REPOSITORY_URL,
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
