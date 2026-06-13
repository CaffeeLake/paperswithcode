"""Set featured_rank 3–5 on coding-agents benchmarks.

Pins SWE-Bench Verified, SWE-Bench Multilingual, and Terminal Bench 2.1 on
the Coding Agents task page while leaving existing ranks 1–2 unchanged.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/set_coding_agents_featured_ranks.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "coding-agents"
FEATURED: list[tuple[str, int]] = [
    ("swe-bench-verified", 3),
    ("swe-bench-multilingual", 4),
    ("terminal-bench-2-1", 5),
]


def main() -> None:
    with db_manager.session_local() as session:
        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).scalar_one()

        for slug, rank in FEATURED:
            row = (
                session.execute(
                    text(
                        """
                    SELECT d.id, d.name, td.featured_rank
                    FROM datasets d
                    JOIN task_datasets td
                      ON td.dataset_id = d.id AND td.task_id = :task_id
                    WHERE d.slug = :slug
                    """
                    ),
                    {"task_id": task_id, "slug": slug},
                )
                .mappings()
                .one()
            )

            logger.info(
                "Before: %s (slug=%s) featured_rank=%s",
                row["name"],
                slug,
                row["featured_rank"],
            )

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
                    "dataset_id": row["id"],
                    "rank": rank,
                },
            )

            logger.info(
                "After: %s featured_rank=%s",
                row["name"],
                rank,
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
