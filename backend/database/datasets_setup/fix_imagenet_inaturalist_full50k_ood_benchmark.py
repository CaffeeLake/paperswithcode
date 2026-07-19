"""Correct dataset 1223 to the MOS/MCM full-50K ImageNet-iNaturalist protocol.

Run from the repository root:

    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/fix_imagenet_inaturalist_full50k_ood_benchmark.py

This script intentionally updates benchmark metadata only. It does not import,
delete, or otherwise modify evaluation rows.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import Task as DBTask

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 317
TASK_SLUG = "anomaly-detection"
DATASET_ID = 1223
DATASET_SLUG = "imagenet-1k-vs-inaturalist-ood"

SOURCE_PAPER_ID = 5641
SOURCE_ARXIV_ID = "2105.01879"
SOURCE_TITLE = (
    "MOS: Towards Scaling Out-of-distribution Detection for Large Semantic Space"
)
SOURCE_REPOSITORY = "https://github.com/deeplearning-wisc/large_scale_ood"

DATASET_NAME = "ImageNet-1K vs iNaturalist OOD (MOS/MCM Full-50K)"
DATASET_FULL_NAME = (
    "ImageNet-1K Full 50K Validation vs Curated iNaturalist OOD (MOS/MCM Protocol)"
)
DATASET_SHORT_DESCRIPTION = (
    "MOS/MCM large-scale OOD protocol using all 50,000 ImageNet-1K validation "
    "images as ID and the curated 10,000-image iNaturalist subset as OOD."
)
DATASET_DESCRIPTION = (
    "Protocol-specific large-scale out-of-distribution detection leaderboard "
    "introduced by MOS and subsequently used by MCM-family work. ImageNet-1K "
    "is the in-distribution dataset: models may train or pretrain as documented "
    "by each source, and evaluation uses all 50,000 images from the ILSVRC2012 "
    "ImageNet-1K validation set as ID examples. The OOD side is the MOS-curated "
    "iNaturalist subset: 10,000 images randomly sampled from 110 manually "
    "selected plant classes absent from ImageNet-1K, with images resized to a "
    "maximum dimension of 800 pixels. The pair therefore contains 60,000 test "
    "images in total. Report per-pair AUROC and FPR95 as percentages. Scores "
    "using OpenOOD v1.5's 45,000-image ID test split with 5,000 reserved "
    "validation images, another iNaturalist subset, another ID dataset, or "
    "aggregates over multiple OOD datasets are not comparable."
)
DATASET_WARNING = (
    "PROTOCOL WARNING: This is the older MOS/MCM full-50K protocol, not "
    "OpenOOD v1.5. Eligible results must evaluate all 50,000 ImageNet-1K "
    "validation images as ID against the MOS-curated 10,000-image iNaturalist "
    "OOD subset drawn from 110 non-overlapping plant classes. Do not add "
    "OpenOOD v1.5 45K-test/5K-validation results, results from an alternate "
    "iNaturalist subset, or multi-dataset aggregate scores."
)
SPLIT_NAME = "ImageNet-1K val (50,000 ID) vs MOS-curated iNaturalist (10,000 OOD)"

METRICS = {
    "AUROC": ("higher_is_better", "percentage"),
    "FPR95": ("lower_is_better", "percentage"),
}


def get_task(session: Session) -> DBTask:
    task = session.get(DBTask, TASK_ID)
    if task is None or task.slug != TASK_SLUG:
        raise RuntimeError(
            f"Expected task id={TASK_ID} slug={TASK_SLUG!r}, found {task!r}"
        )
    return task


def get_source_paper(session: Session) -> DBPaper:
    paper = session.get(DBPaper, SOURCE_PAPER_ID)
    if paper is None:
        raise RuntimeError(f"Source paper id={SOURCE_PAPER_ID} not found")
    if paper.arxiv_id != SOURCE_ARXIV_ID or paper.title != SOURCE_TITLE:
        raise RuntimeError(
            f"Source paper mismatch: id={paper.id}, arxiv={paper.arxiv_id!r}, "
            f"title={paper.title!r}"
        )
    return paper


def get_dataset(session: Session) -> DBDataset:
    dataset = session.get(DBDataset, DATASET_ID)
    if dataset is None:
        raise RuntimeError(f"Dataset id={DATASET_ID} not found")
    if dataset.slug != DATASET_SLUG:
        raise RuntimeError(
            f"Dataset id={DATASET_ID} has slug={dataset.slug!r}; "
            f"expected {DATASET_SLUG!r}"
        )
    slug_owner = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if slug_owner is None or slug_owner.id != DATASET_ID:
        raise RuntimeError(
            f"Slug {DATASET_SLUG!r} is not uniquely owned by dataset {DATASET_ID}"
        )
    return dataset


def get_metric_ids(session: Session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, (direction, scale) in METRICS.items():
        row = session.execute(
            text("SELECT id, direction, scale FROM metrics WHERE name = :name"),
            {"name": name},
        ).one_or_none()
        if row is None:
            raise RuntimeError(f"Required metric {name!r} not found")
        if row.direction != direction or row.scale != scale:
            raise RuntimeError(
                f"Metric {name!r} has direction={row.direction!r}, "
                f"scale={row.scale!r}; expected {direction!r}, {scale!r}"
            )
        metric_ids[name] = int(row.id)
    return metric_ids


def update_dataset(dataset: DBDataset, source_paper: DBPaper) -> None:
    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_FULL_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.warning = DATASET_WARNING
    dataset.url = SOURCE_REPOSITORY
    dataset.homepage = SOURCE_REPOSITORY
    dataset.variant_type = "derived"
    dataset.split_name = SPLIT_NAME
    dataset.modalities = ["Images"]
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.paper_url = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
    dataset.introduced_date = source_paper.date_published
    dataset.introduced_year = source_paper.date_published.year


def link_contract(
    session: Session,
    task_id: int,
    dataset_id: int,
    paper_id: int,
    metric_ids: dict[str, int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_datasets (
                task_id, dataset_id, featured_rank, supports_harness
            )
            VALUES (:task_id, :dataset_id, NULL, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = NULL, supports_harness = FALSE
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )

    allowed_ids = list(metric_ids.values())
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND NOT (metric_id = ANY(:allowed_ids))
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "allowed_ids": allowed_ids,
        },
    )
    for metric_id in allowed_ids:
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {
                "task_id": task_id,
                "dataset_id": dataset_id,
                "metric_id": metric_id,
            },
        )


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        dataset = get_dataset(session)
        metric_ids = get_metric_ids(session)

        update_dataset(dataset, source_paper)
        link_contract(
            session,
            task_id=task.id,
            dataset_id=dataset.id,
            paper_id=source_paper.id,
            metric_ids=metric_ids,
        )
        session.commit()

        logger.info(
            "Corrected dataset id=%s slug=%s source=%s metrics=%s",
            dataset.id,
            dataset.slug,
            dataset.paper_url,
            list(METRICS),
        )


if __name__ == "__main__":
    main()
