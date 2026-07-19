#!/usr/bin/env python3
"""Add the PAMAP2 LOSO activity-classification benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "pamap2"
SOURCE_URL = "https://doi.org/10.1109/ISWC.2012.13"
SOURCE_TITLE = "Introducing a New Benchmarked Dataset for Activity Monitoring"


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces PAMAP2, a wearable-sensor dataset for physical "
                    "activity monitoring recorded from nine participants using "
                    "three inertial measurement units and a heart-rate monitor, "
                    "together with benchmark activity-recognition problems."
                ),
                authors=["Attila Reiss", "Didier Stricker"],
                date_published=date(2012, 6, 1),
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
                INSERT INTO metrics (name, full_name, direction, scale, description)
                VALUES (
                    'Macro F1',
                    'Macro-averaged F1 Score',
                    'higher_is_better',
                    '0-1',
                    'Unweighted mean of the per-class F1 scores.'
                )
                ON CONFLICT (name) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    direction = EXCLUDED.direction,
                    scale = EXCLUDED.scale,
                    description = EXCLUDED.description,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
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
                    introduced_year, modalities, license_name, license_url,
                    split_name, warning, pwc_url
                )
                VALUES (
                    'PAMAP2',
                    :slug,
                    'PAMAP2 Physical Activity Monitoring Dataset',
                    'Wearable-sensor activity-classification benchmark with 18 '
                    'physical activities performed by nine participants wearing '
                    'three inertial measurement units and a heart-rate monitor. '
                    'This leaderboard uses subject-independent leave-one-subject-out '
                    '(LOSO) evaluation and Macro F1.',
                    'Subject-independent wearable human-activity recognition on PAMAP2.',
                    'https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring',
                    'https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring',
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2012-06-01',
                    2012,
                    '["Time Series", "Wearable Sensors", "Inertial Sensors"]'::jsonb,
                    'CC BY 4.0',
                    'https://creativecommons.org/licenses/by/4.0/',
                    'Leave-One-Subject-Out (LOSO)',
                    'Only subject-independent LOSO activity-classification results '
                    'reported with Macro F1 belong on this leaderboard. Clustering '
                    'NMI/ARI and subject-dependent or random-window splits are not comparable.',
                    'https://paperswithcode.com/sota/human-activity-recognition-on-pamap2'
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
                    license_name = EXCLUDED.license_name,
                    license_url = EXCLUDED.license_url,
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
