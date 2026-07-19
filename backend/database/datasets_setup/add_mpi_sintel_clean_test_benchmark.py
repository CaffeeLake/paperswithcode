#!/usr/bin/env python3
"""Add the MPI Sintel Clean hidden-test optical-flow leaderboard.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_mpi_sintel_clean_test_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import get_engine


TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 85620
PARENT_DATASET_ID = 670
DATASET_SLUG = "mpi-sintel-clean-test"
METRIC_NAME = "Average End-Point Error"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/85620"


def main() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        task = (
            connection.execute(
                text("SELECT id, slug FROM tasks WHERE id = :id"), {"id": TASK_ID}
            )
            .mappings()
            .one()
        )
        if task["slug"] != TASK_SLUG:
            raise RuntimeError(f"Task {TASK_ID} is {task['slug']!r}, not {TASK_SLUG!r}")

        paper = (
            connection.execute(
                text("SELECT id, title FROM papers WHERE id = :id"),
                {"id": SOURCE_PAPER_ID},
            )
            .mappings()
            .one()
        )

        dataset_id = connection.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    homepage, parent_dataset_id, variant_type, split_name,
                    introducing_paper_id, introducing_paper_title, paper_url,
                    introduced_year, modalities, warning
                )
                VALUES (
                    'MPI Sintel Clean Test', :slug,
                    'MPI Sintel Clean Pass — Official Hidden Test Set',
                    'The official MPI Sintel optical-flow hidden test-set leaderboard '
                    'for the Clean rendering pass. Methods submit predictions to the '
                    'official evaluation server and are ranked by average end-point '
                    'error in pixels against withheld test ground truth. This row is '
                    'reserved for the standard supervised/general test protocol; '
                    'training-set, Final-pass, and unsupervised-only results belong on '
                    'separate leaderboards.',
                    'Official hidden-test optical-flow evaluation on the Sintel Clean pass.',
                    'http://sintel.is.tue.mpg.de/', :parent_dataset_id, 'split',
                    'Clean pass — official hidden test (supervised/general)',
                    :paper_id, :paper_title, :paper_url, 2012,
                    CAST('["Images", "Video", "Optical Flow"]' AS jsonb),
                    'Only official-server Clean-pass hidden-test results under the '
                    'standard supervised/general protocol are comparable. Do not mix '
                    'Sintel training results, Final-pass scores, or unsupervised-only '
                    'leaderboard entries.'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    homepage = EXCLUDED.homepage,
                    parent_dataset_id = EXCLUDED.parent_dataset_id,
                    variant_type = EXCLUDED.variant_type,
                    split_name = EXCLUDED.split_name,
                    introducing_paper_id = EXCLUDED.introducing_paper_id,
                    introducing_paper_title = EXCLUDED.introducing_paper_title,
                    paper_url = EXCLUDED.paper_url,
                    introduced_year = EXCLUDED.introduced_year,
                    modalities = EXCLUDED.modalities,
                    warning = EXCLUDED.warning,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {
                "slug": DATASET_SLUG,
                "parent_dataset_id": PARENT_DATASET_ID,
                "paper_id": SOURCE_PAPER_ID,
                "paper_title": paper["title"],
                "paper_url": NATIVE_PAPER_URL,
            },
        ).scalar_one()

        metric_id = connection.execute(
            text(
                """
                INSERT INTO metrics (name, full_name, direction, scale, description)
                VALUES (
                    :name, 'Average End-Point Error', 'lower_is_better', 'unbounded',
                    'Mean Euclidean distance in pixels between predicted and ground-truth optical-flow vectors.'
                )
                ON CONFLICT (name) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    direction = EXCLUDED.direction,
                    scale = EXCLUDED.scale,
                    description = EXCLUDED.description,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {"name": METRIC_NAME},
        ).scalar_one()

        connection.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": SOURCE_PAPER_ID, "task_id": TASK_ID},
        )
        connection.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                VALUES (:task_id, :dataset_id, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    supports_harness = FALSE,
                    updated_at = NOW()
                """
            ),
            {"task_id": TASK_ID, "dataset_id": dataset_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "metric_id": metric_id,
            },
        )

    print(
        f"dataset_id={dataset_id} slug={DATASET_SLUG} task_id={TASK_ID} "
        f"metric_id={metric_id}"
    )


if __name__ == "__main__":
    main()
