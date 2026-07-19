#!/usr/bin/env python3
"""Add the supervised leave-one-user-out HHAR benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "hhar"
SOURCE_URL = "https://doi.org/10.1145/2809695.2809718"
SOURCE_TITLE = (
    "Smart Devices are Different: Assessing and Mitigating Mobile Sensing "
    "Heterogeneities for Activity Recognition"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces the Heterogeneity Human Activity Recognition "
                    "dataset and systematically evaluates how sensor, device, "
                    "sampling-rate, and workload heterogeneities affect activity "
                    "recognition across smartphones and smartwatches."
                ),
                authors=[
                    "Allan Stisen",
                    "Henrik Blunck",
                    "Sourav Bhattacharya",
                    "Thor Siiger Prentow",
                    "Mikkel Baun Kjærgaard",
                    "Anind Dey",
                    "Tobias Sonne",
                    "Mads Møller Jensen",
                ],
                date_published=date(2015, 11, 1),
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
                    'HHAR (Leave-One-User-Out)',
                    :slug,
                    'Heterogeneity Human Activity Recognition Dataset',
                    'Smartphone- and smartwatch-based human activity recognition '
                    'dataset designed to expose sensing heterogeneity across users, '
                    'device instances, device models, and sampling behavior. It '
                    'contains accelerometer and gyroscope recordings for six '
                    'activities from nine users. This leaderboard uses supervised '
                    'leave-one-user-out evaluation across the heterogeneous devices.',
                    'Supervised cross-user activity recognition on heterogeneous '
                    'smartphones and smartwatches.',
                    'https://archive.ics.uci.edu/dataset/344/heterogeneity+activity+recognition',
                    'https://archive.ics.uci.edu/dataset/344/heterogeneity+activity+recognition',
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2015-11-01',
                    2015,
                    '["Time Series", "Smartphone", "Smartwatch", "Accelerometer", '
                    '"Gyroscope"]'::jsonb,
                    'Supervised Leave-One-User-Out (LOUO)',
                    'Only supervised leave-one-user-out results that exclude every '
                    'window from the test user during training and report Accuracy '
                    'as a percentage belong here. Random-window or record-level '
                    'splits leak user/session information. Unsupervised or '
                    'semi-supervised domain adaptation, target-user fine-tuning, '
                    'few-shot personalization, leave-one-device/model-out, and '
                    'phone-only or watch-only setups are incompatible and require '
                    'separate leaderboards.',
                    'https://paperswithcode.com/dataset/hhar'
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
