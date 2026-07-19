"""Add the RealVSR benchmark to Video Super-Resolution.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_realvsr_benchmark.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper
from backend.models.database import Task as DBTask
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "video-super-resolution"
SOURCE_URL = (
    "https://openaccess.thecvf.com/content/ICCV2021/html/"
    "Yang_Real-World_Video_Super-Resolution_A_Benchmark_Dataset_and_a_"
    "Decomposition_Based_ICCV_2021_paper.html"
)
REPO_URL = "https://github.com/IanYeung/RealVSR"
METRIC_NAMES = ["PSNR", "SSIM", "LPIPS"]


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def ensure_source_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == SOURCE_URL)
        .one_or_none()
    )
    if paper is not None:
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=(
                "Real-World Video Super-Resolution: A Benchmark Dataset "
                "and a Decomposition Based Learning Scheme"
            ),
            abstract=(
                "Introduces RealVSR, a real-world video super-resolution "
                "dataset built from paired low-resolution and high-resolution "
                "video sequences captured with the multi-camera system of an "
                "iPhone 11 Pro Max, and proposes a decomposition-based "
                "training scheme for robust reconstruction."
            ),
            authors=["Xi Yang", "Wangmeng Xiang", "Hui Zeng", "Lei Zhang"],
            date_published=date(2021, 10, 11),
            github_repository_urls=[REPO_URL],
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external paper id=%s", paper.id)
    return paper


def ensure_dataset(session: Session, source_paper: DBPaper) -> tuple[DBDataset, bool]:
    native_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset)
        .filter(
            (DBDataset.slug == "realvsr")
            | (DBDataset.name.ilike("RealVSR"))
            | (DBDataset.full_name.ilike("Real-world Video Super-Resolution"))
        )
        .order_by(DBDataset.id)
        .first()
    )
    created = dataset is None
    if dataset is None:
        dataset = DBDataset(
            name="RealVSR",
            slug="realvsr",
        )
        session.add(dataset)
        session.flush()

    dataset.full_name = "Real-world Video Super-Resolution"
    dataset.description = (
        "RealVSR is a real-world paired video super-resolution benchmark "
        "introduced at ICCV 2021. It contains 500 low-resolution and "
        "high-resolution sequence pairs captured with synchronized cameras, "
        "with 450 pairs for training and 50 pairs for testing. The source "
        "paper evaluates the benchmark as a real-world paired VSR setting and "
        "reports PSNR, SSIM, and perceptual metrics on the testing set."
    )
    dataset.short_description = (
        "Real-world paired LR-HR video super-resolution benchmark."
    )
    dataset.url = REPO_URL
    dataset.homepage = REPO_URL
    dataset.paper_url = native_url
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2021
    dataset.introduced_date = date(2021, 10, 11)
    dataset.modalities = ["Video"]
    session.flush()
    logger.info(
        "%s dataset %r id=%s",
        "Created" if created else "Reused/updated",
        dataset.name,
        dataset.id,
    )
    return dataset, created


def metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE lower(name) = lower(:name)"),
        {"name": name},
    ).fetchone()
    if row is None:
        if name != "LPIPS":
            raise RuntimeError(f"Required metric {name!r} is missing")
        return int(
            session.execute(
                text(
                    """
                    INSERT INTO metrics
                        (name, full_name, direction, scale, description)
                    VALUES
                        (
                            'LPIPS',
                            'Learned Perceptual Image Patch Similarity',
                            'lower_is_better',
                            'unbounded',
                            'Perceptual similarity metric (lower is better).'
                        )
                    RETURNING id
                    """
                )
            ).scalar_one()
        )
    return int(row[0])


def link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def link_metric(
    session: Session, task_id: int, dataset_id: int, metric_id_: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id_},
    )


def tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
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


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = ensure_source_paper(session)
        dataset, created = ensure_dataset(session, source_paper)
        link_task_dataset(session, task.id, dataset.id)
        metric_ids = [metric_id(session, name) for name in METRIC_NAMES]
        for linked_metric_id in metric_ids:
            link_metric(session, task.id, dataset.id, linked_metric_id)
        tag_source_paper(session, source_paper.id, task.id)
        session.commit()
        logger.info(
            "RealVSR ready: dataset_id=%s slug=%s created=%s metrics=%s paper_url=%s",
            dataset.id,
            dataset.slug,
            created,
            METRIC_NAMES,
            dataset.paper_url,
        )


if __name__ == "__main__":
    main()
