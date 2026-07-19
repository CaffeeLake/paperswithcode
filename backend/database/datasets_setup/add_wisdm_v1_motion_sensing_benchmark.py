#!/usr/bin/env python3
"""Add the subject-independent WISDM v1.1 smartphone benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "wisdm-v1-1-smartphone-accelerometer"
SOURCE_URL = "https://doi.org/10.1145/1964897.1964918"
SOURCE_TITLE = "Activity Recognition Using Cell Phone Accelerometers"


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Describes the original controlled WISDM activity-recognition "
                    "dataset and system, using smartphone accelerometer data from "
                    "participants performing walking, jogging, stair climbing, "
                    "sitting, and standing activities."
                ),
                authors=[
                    "Jennifer R. Kwapisz",
                    "Gary M. Weiss",
                    "Samuel A. Moore",
                ],
                date_published=date(2011, 3, 31),
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
                    url, homepage, introducing_paper_id,
                    introducing_paper_title, paper_url, introduced_date,
                    introduced_year, modalities, split_name, warning, pwc_url
                )
                VALUES (
                    'WISDM v1.1 (Smartphone Accelerometer)',
                    :slug,
                    'WISDM Activity Prediction v1.1 Smartphone Accelerometer Dataset',
                    'Canonical controlled WISDM Activity Prediction release for '
                    'human activity recognition from a smartphone tri-axial '
                    'accelerometer sampled at 20 Hz. It covers six activities: '
                    'walking, jogging, upstairs, downstairs, sitting, and standing. '
                    'This leaderboard uses subject-independent evaluation.',
                    'Cross-subject activity recognition on the controlled WISDM v1.1 '
                    'smartphone-accelerometer release.',
                    'https://www.cis.fordham.edu/wisdm/dataset.php',
                    'https://www.cis.fordham.edu/wisdm/dataset.php',
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2011-03-31',
                    2011,
                    '["Time Series", "Smartphone", "Accelerometer"]'::jsonb,
                    'Subject-independent (cross-subject)',
                    'Only results that keep test subjects entirely out of training '
                    'and report Accuracy as a percentage belong on this leaderboard. '
                    'Random-window or record-level cross-validation is not comparable. '
                    'Do not mix this controlled smartphone-accelerometer v1.1 release '
                    'with Actitracker or the later 51-subject smartphone-and-smartwatch dataset.',
                    'https://paperswithcode.com/dataset/wisdm'
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
