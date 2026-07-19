#!/usr/bin/env python3
"""Add the patient-independent Daphnet FoG AUROC benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "daphnet-freezing-of-gait-loso"
SOURCE_URL = "https://doi.org/10.1109/TITB.2009.2036165"
SOURCE_TITLE = (
    "Wearable Assistant for Parkinson’s Disease Patients With the Freezing "
    "of Gait Symptom"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Describes the Daphnet wearable system and dataset for online "
                    "detection of freezing-of-gait episodes in people with "
                    "Parkinson's disease using triaxial accelerometers on the "
                    "ankle, thigh, and lower back."
                ),
                authors=[
                    "Marc Bächlin",
                    "Meir Plotnik",
                    "Daniel Roggen",
                    "Inbal Maidan",
                    "Jeffrey M. Hausdorff",
                    "Nir Giladi",
                    "Gerhard Tröster",
                ],
                date_published=date(2010, 3, 1),
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
                INSERT INTO metrics (
                    name, full_name, direction, scale, description
                )
                VALUES (
                    'AUROC (0-1)',
                    'Area Under the Receiver Operating Characteristic Curve',
                    'higher_is_better',
                    '0-1',
                    'Area under the window-level ROC curve, represented from 0 to 1.'
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
                    'Daphnet Freezing of Gait (LOSO, 4 s)',
                    :slug,
                    'Daphnet Freezing of Gait Dataset',
                    'Binary freezing-of-gait detection from three triaxial '
                    'accelerometers placed on the ankle, thigh, and lower back of '
                    'people with Parkinson''s disease. The comparable protocol uses '
                    'the eight participants with annotated FoG episodes, 64 Hz '
                    'signals, and leave-one-subject-out evaluation.',
                    'Patient-independent window-level FoG detection on Daphnet.',
                    'https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait',
                    'https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait',
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2010-03-01',
                    2010,
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Clinical"]'::jsonb,
                    'CC BY 4.0',
                    'https://creativecommons.org/licenses/by/4.0/',
                    'LOSO; 4 s windows; 75% overlap; >50% FoG label; 8 FoG-positive patients',
                    'Protocol: discard samples labeled 0 (not part of the experiment); '
                    'use all nine channels from the ankle, thigh, and lower-back '
                    'accelerometers at 64 Hz; segment each recording into 4-second '
                    '(256-sample) windows with a 1-second step (75% overlap); label a '
                    'window FoG only when more than 50% of its samples have label 2, '
                    'otherwise label it non-FoG from label 1; evaluate by '
                    'leave-one-subject-out over the eight participants who exhibit '
                    'FoG (subjects 4 and 10 are excluded). Report window-level AUROC '
                    'on a 0-1 scale. Accuracy is invalid for this imbalanced task. '
                    'Random-window splits, patient-specific folds, different window '
                    'lengths/overlaps, single-sensor inputs, inclusion of non-freezers, '
                    'or event-level/tolerance scoring require separate leaderboards.',
                    'https://paperswithcode.com/dataset/daphnet-freezing-of-gait'
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
