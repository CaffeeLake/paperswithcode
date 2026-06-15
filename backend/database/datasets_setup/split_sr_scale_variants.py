"""Split image SR benchmarks into scale-specific leaderboards (legacy PwC style).

Classical SR benchmarks report PSNR at different upscaling factors (×2, ×4, …).
Legacy PapersWithCode used separate leaderboards per scale, e.g.
"Set5 - 2x upscaling" vs "Set5 - 4x upscaling", with scale-free model names.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/split_sr_scale_variants.py
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 314
METRIC_NAME = "PSNR"

PARENT_DATASETS = [
    (748, "Set5", "set5"),
    (749, "Set14", "set14"),
    (750, "BSD100", "bsd100"),
    (751, "Urban100", "urban100"),
    (752, "Manga109", "manga109"),
]

SCALES = ("2x", "4x")


def _get_metric_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
    ).scalar_one()


def _get_parent(session: Session, parent_id: int) -> DBDataset:
    parent = session.query(DBDataset).filter(DBDataset.id == parent_id).one_or_none()
    if parent is None:
        raise RuntimeError(f"Parent dataset id={parent_id} not found")
    return parent


def _ensure_scale_dataset(
    session: Session,
    parent: DBDataset,
    *,
    scale: str,
    parent_slug: str,
) -> DBDataset:
    name = f"{parent.name} - {scale} upscaling"
    slug = f"{parent_slug}-{scale}-upscaling"
    description = (
        f"{parent.name} benchmark for image super-resolution at {scale} upscaling. "
        f"Results on this leaderboard are comparable only within the same scale factor."
    )

    dataset = session.query(DBDataset).filter(DBDataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = DBDataset(
            name=name,
            slug=slug,
            description=description,
            hf_url=parent.hf_url,
            homepage=parent.homepage,
            paper_url=parent.paper_url,
            introducing_paper_id=parent.introducing_paper_id,
            introducing_paper_title=parent.introducing_paper_title,
            introduced_year=parent.introduced_year,
            parent_dataset_id=parent.id,
            variant_type="variant",
            split_name=f"{scale} upscaling",
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = name
    dataset.description = description
    dataset.parent_dataset_id = parent.id
    dataset.variant_type = "variant"
    dataset.split_name = f"{scale} upscaling"
    dataset.paper_url = parent.paper_url
    dataset.introducing_paper_id = parent.introducing_paper_id
    dataset.introducing_paper_title = parent.introducing_paper_title
    dataset.hf_url = parent.hf_url
    dataset.homepage = parent.homepage
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_task_links(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def _unlink_parent_from_task(session: Session, task_id: int, parent_id: int) -> None:
    session.execute(
        text("DELETE FROM task_datasets WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )
    session.execute(
        text("DELETE FROM task_dataset_metrics WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )


def _scale_from_model_name(model_name: str) -> str:
    if re.search(r"\(×4\)|\(x4\)", model_name, flags=re.IGNORECASE):
        return "4x"
    return "2x"


def _clean_model_name(model_name: str) -> str:
    return re.sub(r"\s*\([×x][24]\)\s*$", "", model_name, flags=re.IGNORECASE).strip()


def _clean_methodology(methodology: str | None) -> str | None:
    if not methodology:
        return methodology
    cleaned = methodology
    for prefix in ("Classical SR ×2; ", "Classical SR ×4; "):
        cleaned = cleaned.replace(prefix, "")
    return cleaned.strip() or None


def _migrate_evaluations(
    session: Session,
    service: EvaluationService,
    *,
    variant_ids: dict[tuple[int, str], int],
) -> None:
    rows = session.execute(
        text(
            """
            SELECT id, dataset_id, model_name, methodology
            FROM evaluations
            WHERE task_id = :task_id
            """
        ),
        {"task_id": TASK_ID},
    ).fetchall()

    touched_variants: set[tuple[int, str]] = set()
    for row in rows:
        parent_id = row.dataset_id
        scale = _scale_from_model_name(row.model_name)
        variant_id = variant_ids[(parent_id, scale)]
        new_model = _clean_model_name(row.model_name)
        new_methodology = _clean_methodology(row.methodology)

        service.update_evaluation(
            evaluation_id=row.id,
            dataset_id=variant_id,
            model_name=new_model,
            methodology=new_methodology,
        )
        touched_variants.add((variant_id, scale))
        logger.info(
            "Moved evaluation %s parent=%s -> %s (%s), model=%r",
            row.id,
            parent_id,
            variant_id,
            scale,
            new_model,
        )

    for variant_id, _scale in sorted(touched_variants):
        service.recalculate_ranks(TASK_ID, variant_id, metric_name=METRIC_NAME)


def main() -> None:
    session = db_manager.session_local()
    try:
        metric_id = _get_metric_id(session)
        variant_ids: dict[tuple[int, str], int] = {}

        for parent_id, _parent_name, parent_slug in PARENT_DATASETS:
            parent = _get_parent(session, parent_id)
            for scale in SCALES:
                child = _ensure_scale_dataset(
                    session, parent, scale=scale, parent_slug=parent_slug
                )
                _ensure_task_links(session, TASK_ID, child.id, metric_id)
                variant_ids[(parent_id, scale)] = child.id
            _unlink_parent_from_task(session, TASK_ID, parent_id)

        service = EvaluationService(session)
        _migrate_evaluations(session, service, variant_ids=variant_ids)
        session.commit()
        logger.info("Image SR scale-variant migration complete")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
