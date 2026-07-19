#!/usr/bin/env python3
"""Add the canonical 12-class LOSO HARTH benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "harth"
SOURCE_URL = "https://doi.org/10.3390/s21237853"
SOURCE_TITLE = "HARTH: A Human Activity Recognition Dataset for Machine Learning"


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces the Human Activity Recognition Trondheim dataset, "
                    "recorded from 22 participants in free-living work settings "
                    "using thigh- and lower-back-mounted triaxial accelerometers "
                    "with expert video annotation of twelve activities."
                ),
                authors=[
                    "Aleksej Logacjov",
                    "Kerstin Bach",
                    "Atle Kongsvold",
                    "Hilde Bremseth Bårdstu",
                    "Paul Jarle Mork",
                ],
                date_published=date(2021, 11, 25),
                github_repository_urls=[
                    "https://github.com/ntnu-ai-lab/harth-ml-experiments"
                ],
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
                    'HARTH (12-class LOSO)',
                    :slug,
                    'Human Activity Recognition Trondheim Dataset',
                    'Free-living human activity classification dataset recorded '
                    'from 22 participants using two triaxial accelerometers fixed '
                    'to the right thigh and lower back. Expert video annotation '
                    'provides twelve activity labels. This leaderboard uses '
                    'leave-one-subject-out evaluation on the full dual-sensor, '
                    'twelve-class task.',
                    'Twelve-class, dual-accelerometer free-living activity recognition '
                    'with leave-one-subject-out evaluation.',
                    'https://archive.ics.uci.edu/dataset/779/harth',
                    'https://github.com/ntnu-ai-lab/harth-ml-experiments',
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2021-11-25',
                    2021,
                    '["Time Series", "Wearable Sensors", "Accelerometer"]'::jsonb,
                    'Leave-One-Subject-Out (LOSO), 12 classes, dual accelerometer',
                    'Only held-out-subject results using the canonical twelve activity '
                    'labels and both thigh and lower-back accelerometers belong on '
                    'this leaderboard. Random-window or record-level splits leak '
                    'subject/session information. Results that merge or omit labels, '
                    'remove rare classes, use a binary or reduced taxonomy, or use '
                    'only one sensor require separate leaderboards.',
                    'https://paperswithcode.com/dataset/harth'
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
