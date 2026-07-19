#!/usr/bin/env python3
"""Add the participant-independent RealWorld HAR benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "realworld-har"
SOURCE_URL = "https://doi.org/10.1109/PERCOM.2016.7456521"
SOURCE_TITLE = (
    "On-body localization of wearable devices: An investigation of "
    "position-aware activity recognition"
)
DATA_URL = (
    "https://www.uni-mannheim.de/dws/research/projects/"
    "activity-recognition/dataset/dataset-realworld/"
)
THUMBNAIL_URL = (
    "https://www.uni-mannheim.de/media/_processed_/d/4/csm_preview_e8b2df8e46.png"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces the RealWorld HAR dataset and studies on-body "
                    "device localization and position-aware activity recognition "
                    "from wearable accelerometer signals collected in naturalistic "
                    "settings."
                ),
                authors=["Timo Sztyler", "Heiner Stuckenschmidt"],
                date_published=date(2016, 3, 14),
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
                    'RealWorld HAR (7-Position LOSO)',
                    :slug,
                    'RealWorld Human Activity Recognition Dataset',
                    'Naturalistic wearable activity data from 15 participants '
                    '(eight men and seven women) performing eight activities: '
                    'climbing stairs down, climbing stairs up, jumping, lying, '
                    'standing, sitting, running/jogging, and walking. Activities '
                    'were recorded for roughly 10 minutes per participant, except '
                    'jumping (about 1.7 minutes), while synchronized devices were '
                    'worn at seven positions: chest, forearm, head, shin, thigh, '
                    'upper arm, and waist. The canonical benchmark uses only the '
                    'triaxial accelerometer at its native 50 Hz, segmented into '
                    '1-second (50-sample) windows with 50% overlap '
                    '(25-sample/0.5-second stride). It trains a separate '
                    'activity classifier for each known position and evaluates '
                    'each with 15-fold leave-one-participant-out validation.',
                    'Eight-class activity recognition from seven known wearable '
                    'positions with participant-independent evaluation.',
                    :data_url,
                    :data_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2016-03-14',
                    2016,
                    '["Time Series", "Wearable Sensors", "Accelerometer"]'::jsonb,
                    '15-subject LOSO; 7 known positions; 1 s/50% overlap',
                    'Report the unweighted mean of seven position-wise, pooled '
                    'out-of-fold eight-class Macro F1 values on a 0-1 scale. For '
                    'each held-out participant, train seven distinct classifiers, '
                    'each using only the same body position from the other 14 '
                    'participants. Fit normalization, feature selection, model '
                    'selection, and augmentation on training participants only. '
                    'Retain all eight labels, all seven positions, accelerometer '
                    'x/y/z only, 50 Hz sampling, 1-second windows, and 50% '
                    'overlap. Exclude randomized or within-participant K-fold '
                    'splits; window-level train/test splitting; a single position '
                    'or a subset of positions; seven-position sensor fusion; '
                    'position-pooled, position-agnostic, or inferred-position '
                    'models; gyroscope, magnetometer, GPS, light, sound, or video '
                    'inputs; altered activity taxonomies, sampling rates, window '
                    'lengths, strides, aggregation rules, accuracy, weighted/micro '
                    'F1, or percentage-scaled scores.',
                    'https://paperswithcode.com/dataset/realworld-har'
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
