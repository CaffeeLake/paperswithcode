"""Set featured benchmark order on the OCR task page.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/set_ocr_featured_ranks.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "ocr"
FEATURED: list[tuple[str, int]] = [
    ("olmocr-bench", 1),
    ("omnidocbench-v1-5", 2),
    ("omnidocbench-v1-6", 3),
]


def main() -> None:
    with db_manager.session_local() as session:
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).scalar_one()

        session.execute(
            text(
                """
                UPDATE task_datasets
                SET featured_rank = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = :task_id
                """
            ),
            {"task_id": task_id},
        )

        for slug, rank in FEATURED:
            dataset_id = session.execute(
                text("SELECT id FROM datasets WHERE slug = :slug"),
                {"slug": slug},
            ).scalar_one()

            session.execute(
                text(
                    """
                    UPDATE task_datasets
                    SET featured_rank = :rank,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE task_id = :task_id
                      AND dataset_id = :dataset_id
                    """
                ),
                {
                    "task_id": task_id,
                    "dataset_id": dataset_id,
                    "rank": rank,
                },
            )

        session.commit()

        rows = (
            session.execute(
                text(
                    """
                SELECT d.name, d.slug, td.featured_rank
                FROM task_datasets td
                JOIN tasks t ON t.id = td.task_id
                JOIN datasets d ON d.id = td.dataset_id
                WHERE t.slug = :slug
                  AND td.featured_rank IS NOT NULL
                ORDER BY td.featured_rank
                """
                ),
                {"slug": TASK_SLUG},
            )
            .mappings()
            .all()
        )

        logger.info("Pinned benchmarks on %s:", TASK_SLUG)
        for row in rows:
            logger.info(
                "  rank=%s %s (slug=%s)",
                row["featured_rank"],
                row["name"],
                row["slug"],
            )


if __name__ == "__main__":
    main()
