"""Add the two-scene Tanks and Temples NVS protocol.

This is the classic full-capture, posed NVS protocol used by 3D Gaussian
Splatting and follow-up work. Scores are averaged across exactly the Train and
Truck scenes. It is intentionally distinct from the existing six-scene,
12-input-view ``Tanks and Temples (6)`` benchmark (dataset id 382).

The introducing paper is the original Tanks and Temples benchmark paper, not
3D Gaussian Splatting, which only established this downstream NVS protocol.
The benchmark paper has no arXiv version; it is indexed as a local external
paper from its canonical DOI.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_tanks_and_temples_train_truck_nvs_benchmark.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "novel-view-synthesis"

SOURCE_URL = "https://doi.org/10.1145/3072959.3073599"
SOURCE_TITLE = "Tanks and Temples: Benchmarking Large-Scale Scene Reconstruction"
SOURCE_DATE = date(2017, 7, 20)
SOURCE_AUTHORS = ["Arno Knapitsch", "Jaesik Park", "Qian-Yi Zhou", "Vladlen Koltun"]
SOURCE_ABSTRACT = (
    "Introduces a benchmark for image-based 3D reconstruction captured in "
    "realistic indoor and outdoor conditions, with high-resolution video "
    "sequences and laser-scanned ground-truth geometry."
)

DATASET_NAME = "Tanks and Temples (Train + Truck NVS)"
DATASET_SLUG = "tanks-and-temples-train-truck-nvs"
DATASET_HOMEPAGE = "https://www.tanksandtemples.org/"
DATASET_SHORT_DESCRIPTION = (
    "Full-capture posed NVS protocol averaged over exactly Train and Truck."
)
DATASET_DESCRIPTION = (
    "The classic full-capture, posed novel-view-synthesis protocol on exactly "
    "the Train and Truck scenes from Tanks and Temples. PSNR, SSIM, and LPIPS "
    "are evaluated on held-out novel views and each leaderboard score is the "
    "arithmetic mean across those two scenes. This is the protocol used by the "
    "original 3D Gaussian Splatting evaluation and follow-up work; it is not "
    "comparable to the six-scene, 12-input-view Tanks and Temples protocol."
)
METRIC_NAMES = ("PSNR", "SSIM", "LPIPS")


def ensure_external_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            (DBPaper.source_url == SOURCE_URL) | (DBPaper.title == SOURCE_TITLE),
        )
        .order_by(DBPaper.id)
        .first()
    )
    if paper is not None:
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=SOURCE_TITLE,
            abstract=SOURCE_ABSTRACT,
            authors=SOURCE_AUTHORS,
            date_published=SOURCE_DATE,
        )
    )
    paper = session.get(DBPaper, int(result.paper.id))
    if paper is None:
        raise RuntimeError("Failed to reload the Tanks and Temples source paper")
    logger.info("Created external source paper id=%s", paper.id)
    return paper


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def get_metric_ids(session: Session) -> dict[str, int]:
    rows = session.execute(
        text("SELECT id, name FROM metrics WHERE name = ANY(:names)"),
        {"names": list(METRIC_NAMES)},
    ).all()
    metric_ids = {str(name): int(metric_id) for metric_id, name in rows}
    missing = set(METRIC_NAMES) - metric_ids.keys()
    if missing:
        raise RuntimeError(f"Missing metrics: {sorted(missing)}")
    return metric_ids


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    native_paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"
    if dataset is None:
        dataset = DBDataset(slug=DATASET_SLUG)
        session.add(dataset)

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.variant_type = "variant"
    dataset.split_name = "Train + Truck (full-capture posed NVS)"
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2017
    dataset.paper_url = native_paper_url
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def link_metadata(
    session: Session,
    task_id: int,
    dataset_id: int,
    source_paper_id: int,
    metric_ids: dict[str, int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = FALSE, featured_rank = NULL
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": source_paper_id, "task_id": task_id},
    )
    for metric_id in metric_ids.values():
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
        )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = ensure_external_paper(session)
        metric_ids = get_metric_ids(session)
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_ids)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s paper_url=%s metrics=%s",
            dataset.name,
            dataset.id,
            dataset.paper_url,
            list(METRIC_NAMES),
        )


if __name__ == "__main__":
    main()
