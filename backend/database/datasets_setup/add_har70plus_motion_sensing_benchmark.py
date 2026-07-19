#!/usr/bin/env python3
"""Add the canonical participant-independent HAR70+ benchmark."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "har70plus"
SOURCE_URL = "https://doi.org/10.3390/s23052368"
SOURCE_TITLE = (
    "Validation of an Activity Type Recognition Model Classifying Daily "
    "Physical Behavior in Older Adults: The HAR70+ Model"
)
HERO_URL = (
    "https://mdpi-res.com/d_attachment/sensors/sensors-23-02368/"
    "article_deploy/html/images/sensors-23-02368-g001.png"
)


def main() -> None:
    db = next(get_database_session())
    try:
        source = ExternalResourceService(db).add_external_resource(
            ExternalResourceInput(
                source_url=SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=(
                    "Introduces and validates HAR70+, a professionally annotated "
                    "dual-accelerometer dataset and activity-recognition model for "
                    "fit-to-frail adults aged 70 to 95, including participants who "
                    "use walking aids."
                ),
                authors=[
                    "Astrid Ustad",
                    "Aleksej Logacjov",
                    "Stine Øverengen Trollebø",
                    "Pernille Thingstad",
                    "Beatrix Vereijken",
                    "Kerstin Bach",
                    "Nina Skjæret Maroni",
                ],
                date_published=date(2023, 2, 21),
                thumbnail_url=HERO_URL,
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
                    url, homepage, image_url, thumbnail_url, verified_image_url,
                    introducing_paper_id, introducing_paper_title, paper_url,
                    introduced_date, introduced_year, modalities, license_name,
                    license_url, split_name, warning, pwc_url
                )
                VALUES (
                    'HAR70+ (4-class LOSO)',
                    :slug,
                    'Human Activity Recognition 70+ Dataset',
                    'Professionally video-annotated activity recordings from 18 '
                    'fit-to-frail adults aged 70 to 95, including five participants '
                    'using walking aids. Two Axivity AX3 triaxial accelerometers on '
                    'the right thigh and lower back record at 50 Hz during a '
                    'semi-structured free-living protocol. The canonical leaderboard '
                    'uses participant-held-out evaluation of four merged activity types.',
                    'Participant-independent physical-behavior classification for '
                    'older adults using thigh and lower-back accelerometers.',
                    'https://archive.ics.uci.edu/dataset/780/har70',
                    'https://github.com/ntnu-ai-lab/harth-ml-experiments/tree/v1.2',
                    :hero_url,
                    :hero_url,
                    :hero_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2023-02-21',
                    2023,
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Older Adults"]'::jsonb,
                    'CC BY 4.0',
                    'https://creativecommons.org/licenses/by/4.0/',
                    'HAR70+ LOSO + HARTH v1.2; 5 s non-overlap; 4 merged classes',
                    'Protocol: use all six 50 Hz channels from the right-thigh and '
                    'lower-back accelerometers; segment recordings into non-overlapping '
                    '5-second (250-sample) windows and assign the dominant sample label. '
                    'Merge walking, stair ascent, and stair descent into Walking; merge '
                    'standing and shuffling into Standing; retain Sitting and Lying. '
                    'For every HAR70+ test participant, train without any data from '
                    'that participant, using the other 17 HAR70+ participants together '
                    'with the 22 HARTH v1.2 participants, as in the introducing paper. '
                    'The trained label space also contains Running and Cycling from '
                    'HARTH, although HAR70+ has no test examples of them. Report '
                    'overall Accuracy as a percentage across held-out HAR70+ windows. '
                    'Random-window splits, participant overlap, HAR70+-only training, '
                    'single-sensor inputs, overlapping or differently sized windows, '
                    'the unmerged seven-label taxonomy, walking-aid-only subsets, or '
                    'macro/per-class metrics require separate leaderboards.',
                    'https://paperswithcode.com/dataset/har70'
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
