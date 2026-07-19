#!/usr/bin/env python3
"""Add the canonical UniMiB-SHAR AF-17 LOSO benchmark."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.database.papers_setup.add_missing_dataset_papers import (
    fetch_and_add_paper,
)
from backend.models.database import Paper as DBPaper
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "unimib-shar"
ARXIV_ID = "1611.07688"
SOURCE_TITLE = (
    "UniMiB SHAR: a new dataset for human activity recognition using "
    "acceleration data from smartphones"
)
DATA_URL = "http://www.sal.disco.unimib.it/technologies/unimib-shar/"
THUMBNAIL_URL = (
    "https://mdpi-res.com/d_attachment/applsci/applsci-07-01101/"
    "article_deploy/html/images/applsci-07-01101-g003.png"
)


async def main() -> None:
    db = next(get_database_session())
    try:
        paper = (
            db.query(DBPaper)
            .filter(
                DBPaper.arxiv_id == ARXIV_ID,
                DBPaper.is_latest_version.is_(True),
            )
            .first()
        )
        if paper is None:
            paper = await fetch_and_add_paper(
                ArxivService(), PaperService(db), ARXIV_ID
            )
        if paper is None:
            raise RuntimeError(f"Could not index source paper {ARXIV_ID}")

        paper_id = paper.id
        native_paper_url = f"https://paperswithcode.co/paper/{ARXIV_ID}"
        db.execute(
            text(
                """
                UPDATE papers
                SET thumbnail_url = :thumbnail_url,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :paper_id
                """
            ),
            {"thumbnail_url": THUMBNAIL_URL, "paper_id": paper_id},
        )

        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).scalar_one()
        metric_id = db.execute(
            text(
                """
                SELECT id
                FROM metrics
                WHERE name = 'Macro Accuracy'
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
                    'UniMiB-SHAR (AF-17 LOSO)',
                    :slug,
                    'University of Milano Bicocca Smartphone-based Human '
                    'Activity Recognition Dataset',
                    'The balanced UniMiB-SHAR release contains 11,771 '
                    'pre-segmented examples from 30 healthy participants '
                    '(24 women and six men, ages 18 to 60). AF-17 jointly '
                    'recognizes nine activities of daily living '
                    '(StandingUpFS, StandingUpFL, Walking, Running, GoingUpS, '
                    'Jumping, GoingDownS, LyingDownFS, SittingDown) and eight '
                    'simulated falls (FallingForw, FallingRight, FallingBack, '
                    'HittingObstacle, FallingWithPS, FallingBackSC, Syncope, '
                    'FallingLeft). A Samsung Galaxy Nexus I9250 with a Bosch '
                    'BMA220 triaxial accelerometer was carried in a front '
                    'trouser pocket, with left and right pockets both used. '
                    'Signals were resampled to 50 Hz and gravity was removed '
                    'using a 0.3 Hz Butterworth low-pass estimate. Each released '
                    'example is a peak-centered 3-second event window with 151 '
                    'samples per axis; these are event windows, not a fixed '
                    'stride sliding-window stream. Evaluation uses 30-fold '
                    'leave-one-subject-out cross-validation.',
                    'Seventeen-class joint ADL and fall recognition from '
                    'peak-centered smartphone accelerometer windows under LOSO.',
                    :data_url,
                    :data_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2016-11-23',
                    2016,
                    '["Time Series", "Smartphone Sensors", "Accelerometer"]'::jsonb,
                    'AF-17; 30-subject LOSO; 151 samples at 50 Hz',
                    'Report the unweighted mean of the 30 held-out-subject '
                    'AF-17 macro-average accuracies as a percentage from 0 to '
                    '100. Macro accuracy is the arithmetic mean of the 17 '
                    'per-class recalls. Use the balanced 11,771-window release, '
                    'all 17 fine-grained labels, both front-pocket sides, and '
                    'the released gravity-removed triaxial 151-sample windows. '
                    'All preprocessing fitting, feature selection, model '
                    'selection, and augmentation must exclude the held-out '
                    'subject. Exclude sample-random or stratified K-fold splits; '
                    'fixed subject splits that are not full LOSO; the unbalanced '
                    'original release; AF-2 fall-vs-ADL, A-9 ADL-only, F-8 '
                    'fall-only, binary, merged, reduced, or relabeled tasks; '
                    'magnitude-only inputs; audio or other sensors; newly '
                    're-windowed streams; altered sampling/window lengths; '
                    'ordinary micro accuracy, F1, balanced accuracy with a '
                    'different definition, fold-pooled aggregation, and '
                    '0-1-scaled scores.',
                    'https://paperswithcode.com/dataset/unimib-shar'
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
    asyncio.run(main())
