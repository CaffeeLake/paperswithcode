"""Add the ImageNet-1K ID versus Textures OOD benchmark from MOS.

This is the legacy MOS/MCM protocol: all 50,000 ImageNet-1K validation
images are the ID test set and all 5,640 Describable Textures Dataset images
are the OOD test set. It is not OpenOOD v1.5's 45k-test/5k-validation split.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/datasets_setup/add_imagenet_textures_ood_benchmark.py
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.datasets_setup.add_imagenet_places_ood_benchmark import (
    SOURCE_ARXIV_ID,
    ensure_metrics,
    get_source_paper,
    get_task,
    link_metadata,
)
from backend.models.database import Dataset as DBDataset
from backend.models.database import Paper as DBPaper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATASET_ID = 1226
DATASET_NAME = "ImageNet-1K vs Textures OOD (MOS protocol)"
DATASET_SLUG = "imagenet-1k-vs-textures-ood"
DATASET_HOMEPAGE = "https://github.com/deeplearning-wisc/large_scale_ood"
DATASET_SHORT_DESCRIPTION = (
    "MOS/MCM evaluation using all 50,000 ImageNet-1K validation images as ID "
    "and all 5,640 Describable Textures Dataset images as OOD."
)
DATASET_DESCRIPTION = (
    "Out-of-distribution detection under the fixed large-scale protocol "
    "introduced by MOS and subsequently used by MCM-style evaluations. The ID "
    "test set is the complete 50,000-image ImageNet-1K validation split, and "
    "the OOD test set is the complete 5,640-image Describable Textures Dataset "
    "(DTD), giving 55,640 scored images for the pair. Scores using OpenOOD "
    "v1.5's 45,000-image ID test and 5,000-image ID validation split, a "
    "different Textures subset, another ID dataset, another OOD component, or "
    "an aggregate over multiple OOD datasets are not comparable and must not "
    "be added. Every row must document its checkpoint, backbone, classifier "
    "training, outlier exposure or auxiliary data, and test-time adaptation or "
    "tuning in the model metadata."
)
DATASET_WARNING = (
    "Legacy MOS/MCM full-50k protocol—not OpenOOD v1.5. Only report results "
    "using all 50,000 ImageNet-1K validation images and all 5,640 DTD images; "
    "do not mix in OpenOOD's 45k-test/5k-validation results or alternate "
    "Textures subsets."
)


def ensure_dataset(session: Session, source_paper: DBPaper) -> DBDataset:
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == DATASET_SLUG).one_or_none()
    )
    if dataset is None:
        raise RuntimeError(
            f"Expected existing dataset id={DATASET_ID}, slug={DATASET_SLUG!r}"
        )
    if dataset.id != DATASET_ID:
        raise RuntimeError(
            f"Expected dataset id={DATASET_ID}, found id={dataset.id} for "
            f"slug={DATASET_SLUG!r}"
        )

    dataset.name = DATASET_NAME
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = DATASET_HOMEPAGE
    dataset.homepage = DATASET_HOMEPAGE
    dataset.variant_type = "variant"
    dataset.split_name = (
        "ImageNet-1K validation (all 50,000 ID images); "
        "Describable Textures Dataset (all 5,640 OOD images)"
    )
    dataset.warning = DATASET_WARNING
    dataset.introducing_paper_id = source_paper.id
    dataset.introducing_paper_title = source_paper.title
    dataset.introduced_year = 2021
    dataset.introduced_date = source_paper.date_published
    dataset.paper_url = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
    session.flush()
    logger.info("Upserted dataset %s (id=%s)", dataset.name, dataset.id)
    return dataset


def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)
        source_paper = get_source_paper(session)
        metric_ids = ensure_metrics(session)
        expected_metric_ids = {"FPR95": 411, "AUROC": 412}
        if metric_ids != expected_metric_ids:
            raise RuntimeError(
                f"Metric ID mismatch: found {metric_ids}, "
                f"expected {expected_metric_ids}"
            )
        dataset = ensure_dataset(session, source_paper)
        link_metadata(session, task.id, dataset.id, source_paper.id, metric_ids)
        session.commit()
        logger.info(
            "%s ready: dataset_id=%s slug=%s paper_url=%s metrics=%s",
            dataset.name,
            dataset.id,
            dataset.slug,
            dataset.paper_url,
            metric_ids,
        )


if __name__ == "__main__":
    main()
