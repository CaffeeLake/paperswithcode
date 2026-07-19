"""Add DIV2K-Val (Real-ESRGAN ×4) to Image Super-Resolution.

Synthetic ×4 super-resolution benchmark used by ASASR, SeeSR, DreamClear, and
related methods: 3,000 patches sampled from DIV2K + LSDIR validation images with
Real-ESRGAN higher-order degradation (HQ 1024×1024, LQ 256×256). Distinct from
legacy bicubic "DIV2K val - 4x upscaling" leaderboards.

Source paper: NTIRE 2017 Challenge on Single Image Super-Resolution: Dataset and
Study (introduces DIV2K) — not ASASR/SeeSR/DreamClear evaluation papers.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_div2k_val_real_esrgan_benchmark.py
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

TASK_ID = 314
TASK_SLUG = "image-super-resolution"

SOURCE_URL = "https://doi.org/10.1109/CVPRW.2017.150"
SOURCE_TITLE = (
    "NTIRE 2017 Challenge on Single Image Super-Resolution: Dataset and Study"
)
SOURCE_DATE = date(2017, 7, 1)
SOURCE_AUTHORS = ["Eirikur Agustsson", "Radu Timofte"]
SOURCE_ABSTRACT = (
    "Introduces DIV2K, a large dataset of diverse 2K-resolution RGB images "
    "collected for the NTIRE 2017 single-image super-resolution challenge, "
    "with 800 training, 100 validation, and 100 test images."
)

DATASET_SLUG = "div2k-val-real-esrgan-x4"
DATASET_NAME = "DIV2K-Val (Real-ESRGAN ×4)"
DATASET_FULL_NAME = "DIV2K Validation (Real-ESRGAN ×4 synthetic degradation)"
DATASET_HOMEPAGE = "https://data.vision.ee.ethz.ch/cvl/DIV2K/"
DATASET_URL = DATASET_HOMEPAGE

DATASET_DESCRIPTION = (
    "Synthetic ×4 image super-resolution benchmark on DIV2K validation content "
    "with Real-ESRGAN higher-order degradation. Following ASASR, SeeSR, and "
    "DreamClear, 3,000 test patches are sampled from DIV2K and LSDIR validation "
    "images: high-quality crops at 1024×1024 and low-quality inputs at 256×256 "
    "(×4 scale). Results are comparable only within this Real-ESRGAN synthetic "
    "protocol — not with legacy bicubic DIV2K val ×4 upscaling leaderboards."
)
DATASET_SHORT_DESCRIPTION = (
    "3K synthetic ×4 patches (DIV2K+LSDIR val) with Real-ESRGAN degradation."
)

METRIC_NAMES = [
    "PSNR",
    "SSIM",
    "LPIPS",
    "DISTS",
    "MANIQA",
    "MUSIQ",
    "CLIPIQA+",
]

METRIC_SPECS = {
    "DISTS": {
        "direction": "lower_is_better",
        "full_name": "Deep Image Structure and Texture Similarity",
        "scale": "unbounded",
        "description": (
            "Full-reference perceptual similarity metric combining structure "
            "and texture cues; lower is better."
        ),
    },
    "MANIQA": {
        "direction": "higher_is_better",
        "full_name": "Multi-dimension Attention Network for Image Quality Assessment",
        "scale": "0-1",
        "description": (
            "No-reference image quality metric based on multi-dimension attention; "
            "higher is better."
        ),
    },
    "CLIPIQA+": {
        "direction": "higher_is_better",
        "full_name": "CLIP-based Image Quality Assessment Plus",
        "scale": "0-1",
        "description": (
            "No-reference image quality metric using CLIP-based perceptual "
            "features; higher is better."
        ),
    },
}


def ensure_external_paper(session: Session) -> DBPaper:
    paper = (
        session.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.source_url == SOURCE_URL,
        )
        .one_or_none()
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
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Created external paper id=%s", paper.id)
    return paper


def paper_url(paper: DBPaper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.id == TASK_ID).one_or_none()
    if task is None:
        task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task id={TASK_ID} / slug={TASK_SLUG!r} not found")
    return task


def ensure_metric(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row:
        return int(row[0])

    spec = METRIC_SPECS.get(name)
    if spec is None:
        raise RuntimeError(f"Unknown metric {name!r} and no creation spec provided")

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        {"name": name, **spec},
    ).scalar_one()
    logger.info("Created metric %s (id=%s)", name, metric_id)
    return int(metric_id)


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    native_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=DATASET_NAME,
            slug=DATASET_SLUG,
            full_name=DATASET_FULL_NAME,
            description=DATASET_DESCRIPTION,
            short_description=DATASET_SHORT_DESCRIPTION,
            url=DATASET_URL,
            homepage=DATASET_HOMEPAGE,
            paper_url=native_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=2017,
            variant_type="variant",
            split_name="Val (Real-ESRGAN ×4)",
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.name = DATASET_NAME
        dataset.full_name = DATASET_FULL_NAME
        dataset.description = DATASET_DESCRIPTION
        dataset.short_description = DATASET_SHORT_DESCRIPTION
        dataset.url = DATASET_URL
        dataset.homepage = DATASET_HOMEPAGE
        dataset.paper_url = native_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or 2017
        dataset.variant_type = "variant"
        dataset.split_name = "Val (Real-ESRGAN ×4)"
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


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
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
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
        source_paper = ensure_external_paper(session)
        dataset = ensure_dataset(session, source_paper)
        link_task_dataset(session, task.id, dataset.id)
        tag_source_paper(session, source_paper.id, task.id)

        metric_ids: dict[str, int] = {}
        for metric_name in METRIC_NAMES:
            metric_ids[metric_name] = ensure_metric(session, metric_name)
            link_metric(session, task.id, dataset.id, metric_ids[metric_name])

        session.commit()
        logger.info(
            "%s ready: dataset_id=%s slug=%s paper_id=%s paper_url=%s metrics=%s",
            DATASET_NAME,
            dataset.id,
            dataset.slug,
            source_paper.id,
            dataset.paper_url,
            METRIC_NAMES,
        )


if __name__ == "__main__":
    main()
