"""Add the two-scene Deep Blending benchmark used by classic 3DGS.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_deep_blending_nvs_benchmark.py
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

TASK_SLUG = "novel-view-synthesis"
DATASET_NAME = "Deep Blending (DrJohnson + Playroom NVS)"
DATASET_SLUG = "deep-blending-drjohnson-playroom-nvs"
SOURCE_URL = "https://discovery.ucl.ac.uk/id/eprint/10117776/"
SOURCE_PROJECT_URL = "https://repo-sam.inria.fr/fungraph/deep-blending/"
SOURCE_REPOSITORY_URL = "https://github.com/Phog/DeepBlending"
SOURCE_TITLE = "Deep Blending for Free-Viewpoint Image-Based Rendering"
SOURCE_DATE = date(2018, 11, 1)
SOURCE_AUTHORS = [
    "Peter Hedman",
    "Julien Philip",
    "True Price",
    "Jan-Michael Frahm",
    "George Drettakis",
    "Gabriel Brostow",
]
SOURCE_ABSTRACT = (
    "Free-viewpoint image-based rendering (IBR) is a standing challenge. IBR "
    "methods combine warped versions of input photos to synthesize a novel "
    "view. The image quality of this combination is directly affected by "
    "geometric inaccuracies of multi-view stereo (MVS) reconstruction and by "
    "view- and image-dependent effects that produce artifacts when "
    "contributions from different input views are blended. We present a new "
    "deep learning approach to blending for IBR, in which we use held-out real "
    "image data to learn blending weights to combine input photo "
    "contributions. Our Deep Blending method requires us to address several "
    "challenges to achieve our goal of interactive free-viewpoint IBR "
    "navigation. We first need to provide sufficiently accurate geometry so "
    "the Convolutional Neural Network (CNN) can succeed in finding correct "
    "blending weights. We do this by combining two different MVS "
    "reconstructions with complementary accuracy vs. completeness tradeoffs. "
    "To tightly integrate learning in an interactive IBR system, we need to "
    "adapt our rendering algorithm to produce a fixed number of input layers "
    "that can then be blended by the CNN. We generate training data with a "
    "variety of captured scenes, using each input photo as ground truth in a "
    "held-out approach. We also design the network architecture and the "
    "training loss to provide high quality novel view synthesis, while "
    "reducing temporal flickering artifacts. Our results demonstrate "
    "free-viewpoint IBR in a wide variety of scenes, clearly surpassing "
    "previous methods in visual quality, especially when moving far from the "
    "input cameras."
)
METRIC_NAMES = ("PSNR", "SSIM", "LPIPS")


def _get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def _ensure_source_paper(session: Session) -> DBPaper:
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
        logger.info("Reusing external paper id=%s title=%r", paper.id, paper.title)
        if paper.source_url != SOURCE_URL:
            paper.source_url = SOURCE_URL

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=SOURCE_URL,
            title=SOURCE_TITLE,
            abstract=SOURCE_ABSTRACT,
            authors=SOURCE_AUTHORS,
            date_published=SOURCE_DATE,
            github_repository_urls=[SOURCE_REPOSITORY_URL],
        )
    )
    paper = session.query(DBPaper).filter(DBPaper.id == int(result.paper.id)).one()
    logger.info("Ensured external paper id=%s", paper.id)
    return paper


def _ensure_dataset(session: Session, paper: DBPaper) -> tuple[DBDataset, bool]:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    created = dataset is None
    if dataset is None:
        dataset = DBDataset(name=DATASET_NAME, slug=DATASET_SLUG)
        session.add(dataset)
        session.flush()

    description = (
        "Novel-view synthesis on the Deep Blending captures using the classic "
        "3D Gaussian Splatting full-capture posed-camera protocol. Results are "
        "the unweighted mean over exactly the DrJohnson and Playroom scenes; "
        "no other Deep Blending scenes are included."
    )
    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = description
    dataset.short_description = (
        "Full-capture posed NVS averaged over DrJohnson and Playroom only."
    )
    dataset.homepage = SOURCE_PROJECT_URL
    dataset.paper_url = f"https://paperswithcode.co/paper/{paper.id}"
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = SOURCE_DATE.year
    dataset.modalities = ["Images"]
    session.flush()
    logger.info(
        "%s dataset id=%s slug=%s",
        "Created" if created else "Updated",
        dataset.id,
        dataset.slug,
    )
    return dataset, created


def _link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets
                (task_id, dataset_id, supports_harness, featured_rank)
            VALUES (:task_id, :dataset_id, FALSE, NULL)
            ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                supports_harness = FALSE,
                featured_rank = NULL
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def _link_metrics(session: Session, task_id: int, dataset_id: int) -> None:
    rows = session.execute(
        text("SELECT id, name FROM metrics WHERE name = ANY(:names)"),
        {"names": list(METRIC_NAMES)},
    ).mappings()
    metric_ids = {row["name"]: int(row["id"]) for row in rows}
    missing = set(METRIC_NAMES) - metric_ids.keys()
    if missing:
        raise RuntimeError(f"Required metrics missing: {sorted(missing)}")

    for metric_name in METRIC_NAMES:
        session.execute(
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
                "metric_id": metric_ids[metric_name],
            },
        )


def _tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
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
        task = _get_task(session)
        paper = _ensure_source_paper(session)
        dataset, created = _ensure_dataset(session, paper)
        _link_task_dataset(session, task.id, dataset.id)
        _link_metrics(session, task.id, dataset.id)
        _tag_source_paper(session, paper.id, task.id)
        session.commit()
        logger.info(
            "Deep Blending benchmark ready: dataset_id=%s created=%s "
            "paper_url=%s metrics=%s",
            dataset.id,
            created,
            dataset.paper_url,
            METRIC_NAMES,
        )


if __name__ == "__main__":
    main()
