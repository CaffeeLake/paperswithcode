#!/usr/bin/env python3
"""Add the MPI Sintel Clean official-test unsupervised leaderboard.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_mpi_sintel_clean_unsupervised_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import get_engine


TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 85620
PARENT_DATASET_ID = 670
DATASET_SLUG = "mpi-sintel-clean-unsupervised"
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
        metric = (
            connection.execute(
                text(
                    """
                SELECT id, direction
                FROM metrics
                WHERE name = :name
                """
                ),
                {"name": METRIC_NAME},
            )
            .mappings()
            .one()
        )
        if metric["direction"] != "lower_is_better":
            raise RuntimeError(
                f"Metric {METRIC_NAME!r} has direction {metric['direction']!r}"
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
                    'MPI Sintel Clean Unsupervised', :slug,
                    'MPI Sintel Clean Pass — Official Test, Unsupervised Protocol',
                    'The unsupervised optical-flow leaderboard for the MPI Sintel '
                    'Clean-pass test set. Following the legacy benchmark convention, '
                    'predictions are evaluated on the withheld Sintel test ground truth '
                    'through the official evaluation server and reported as average '
                    'end-point error in pixels. Eligible methods do not use target '
                    'Sintel benchmark ground-truth flow for supervision, model '
                    'selection, or fine-tuning.',
                    'Official Sintel Clean test-server results without target-ground-truth supervision.',
                    'http://sintel.is.tue.mpg.de/', :parent_dataset_id, 'variant',
                    'Clean pass — official hidden test (unsupervised)',
                    :paper_id, :paper_title, :paper_url, 2012,
                    CAST('["Images", "Video", "Optical Flow"]' AS jsonb),
                    'Only Clean-pass official-test results from methods with no target '
                    'Sintel ground-truth supervision or fine-tuning are comparable. Do '
                    'not mix supervised/fine-tuned rows, Sintel training-set scores, or '
                    'Final-pass results into this leaderboard.'
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
                "metric_id": metric["id"],
            },
        )

    print(
        f"dataset_id={dataset_id} slug={DATASET_SLUG} task_id={TASK_ID} "
        f"metric_id={metric['id']} metric={METRIC_NAME!r}"
    )


if __name__ == "__main__":
    main()
