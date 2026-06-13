"""Remove the generic CharXiv parent dataset after DQ/RQ split.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/remove_charxiv_parent.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PARENT_DATASET_ID = 432
CHILD_DATASET_IDS = [731, 732]
INTRODUCING_PAPER_ID = 33745
PAPER_DATASET_IDS_TO_MIGRATE = [33745, 83018]


def _migrate_paper_datasets(session: Session) -> None:
    for paper_id in PAPER_DATASET_IDS_TO_MIGRATE:
        has_rq_eval = session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM evaluations
                    WHERE paper_id = :p AND dataset_id = :rq
                )
                """
            ),
            {"p": paper_id, "rq": CHILD_DATASET_IDS[1]},
        ).scalar_one()

        target_ids = CHILD_DATASET_IDS if paper_id == INTRODUCING_PAPER_ID else []
        if has_rq_eval:
            target_ids = [CHILD_DATASET_IDS[1]]
        elif paper_id != INTRODUCING_PAPER_ID:
            continue

        for dataset_id in target_ids:
            session.execute(
                text(
                    """
                    INSERT INTO paper_datasets (paper_id, dataset_id)
                    VALUES (:p, :d)
                    ON CONFLICT (paper_id, dataset_id) DO NOTHING
                    """
                ),
                {"p": paper_id, "d": dataset_id},
            )
            logger.info(
                "Linked paper %s -> dataset %s in paper_datasets",
                paper_id,
                dataset_id,
            )

    deleted = session.execute(
        text("DELETE FROM paper_datasets WHERE dataset_id = :d"),
        {"d": PARENT_DATASET_ID},
    ).rowcount
    logger.info("Removed %s paper_datasets rows from parent CharXiv", deleted)


def main() -> None:
    session = db_manager.session_local()
    try:
        parent = (
            session.query(DBDataset)
            .filter(DBDataset.id == PARENT_DATASET_ID, DBDataset.slug == "charxiv")
            .one_or_none()
        )
        if parent is None:
            logger.info("Parent CharXiv dataset already removed")
            return

        eval_count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
            {"d": PARENT_DATASET_ID},
        ).scalar_one()
        if eval_count:
            raise RuntimeError(
                f"Refusing to delete parent CharXiv: {eval_count} evaluations remain"
            )

        for child_id in CHILD_DATASET_IDS:
            session.execute(
                text("UPDATE datasets SET parent_dataset_id = NULL WHERE id = :id"),
                {"id": child_id},
            )

        _migrate_paper_datasets(session)
        session.delete(parent)
        session.commit()
        logger.info("Deleted parent CharXiv dataset (id=%s)", PARENT_DATASET_ID)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
