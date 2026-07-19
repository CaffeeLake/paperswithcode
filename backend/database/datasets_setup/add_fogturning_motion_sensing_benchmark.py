#!/usr/bin/env python3
"""Add the patient-independent FoGTurning window-classification benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "fogturning"
SOURCE_URL = "https://doi.org/10.3389/fnins.2022.832463"
SOURCE_TITLE = (
    "A Public Data Set of Videos, Inertial Measurement Unit, and Clinical "
    "Scales of Freezing of Gait in Individuals With Parkinson's Disease "
    "During a Turning-In-Place Task"
)
DATA_URL = "https://doi.org/10.6084/m9.figshare.14984667"
THUMBNAIL_URL = (
    "https://www.frontiersin.org/files/Articles/832463/"
    "fnins-16-832463-HTML/image_m/fnins-16-832463-g001.jpg"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces an open dataset of synchronized video, "
                    "single-shank inertial signals, expert freezing-of-gait "
                    "annotations, and clinical scales from 35 people with "
                    "Parkinson's disease performing turns in place."
                ),
                authors=[
                    "Caroline Ribeiro De Souza",
                    "Runfeng Miao",
                    "Júlia Ávila De Oliveira",
                    "Andrea Cristina De Lima-Pardini",
                    "Débora Fragoso De Campos",
                    "Carla Silva-Batista",
                    "Luis Teixeira",
                    "Solaiman Shokur",
                    "Bouri Mohamed",
                    "Daniel Boari Coelho",
                ],
                date_published=date(2022, 2, 23),
                thumbnail_url=THUMBNAIL_URL,
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
                WHERE name = 'Macro F1'
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
                    'FoGTurning (Window LOSO)',
                    :slug,
                    'FoGTurning Turning-in-Place Freezing of Gait Dataset',
                    'Binary freezing-of-gait window classification from 35 '
                    'people with Parkinson''s disease (16 women and 19 men, '
                    'ages 44 to 84) assessed ON dopaminergic medication. Each '
                    'participant completed one to three 2-minute trials of '
                    'alternating 360-degree right and left turns in place. A '
                    'single Physilog 5 IMU on the most affected shank recorded '
                    'triaxial acceleration and angular velocity at 128 Hz; the '
                    'released signals were fourth-order zero-phase low-pass '
                    'filtered at 60 Hz. Two movement-disorder specialists '
                    'marked sample-level FoG by consensus from synchronized '
                    'video, combining akinetic, trembling, and festinating FoG '
                    'as one positive class. This leaderboard uses all released '
                    'trials, 2-second (256-sample) windows with 75% overlap '
                    '(64-sample/0.5-second stride), majority sample labels, and '
                    '35-fold leave-one-participant-out evaluation.',
                    'Binary FoG detection during turning from a single '
                    'most-affected-shank IMU with 35-subject LOSO evaluation.',
                    :data_url,
                    :data_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2022-02-23',
                    2022,
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Gyroscope", "Inertial Measurement Unit"]'::jsonb,
                    '35-subject LOSO; 128 Hz; 2 s/75% overlap; majority label',
                    'Report pooled out-of-fold binary Macro F1 on a 0-1 scale; '
                    'each participant must be held out once, and all model '
                    'selection, normalization fitting, resampling, and data '
                    'augmentation must use training participants only. Retain '
                    'the released single most-affected-shank accelerometer and '
                    'gyroscope channels, 128 Hz processed signals, all available '
                    'turning-in-place trials, 2-second windows, 75% overlap, and '
                    'majority expert labels. Do not mix in Daphnet, OdayFoG, '
                    'FoG-STAR, tDCSFoG, DeFOG, or any other cohort. Exclude '
                    'patient-mixed random/K-fold splits, 64 Hz variants, other '
                    'window lengths/strides/label thresholds, sensor subsets, '
                    'medication-state changes, event-level or episode-count '
                    'scores, FoG-ratio/severity correlations, segment F1, '
                    'per-fold-only averaging, and percentage-scaled F1.',
                    'https://paperswithcode.com/dataset/fogturning'
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
                "data_url": DATA_URL,
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
