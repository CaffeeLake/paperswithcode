"""Add the MPI Sintel Final unsupervised optical-flow benchmark.

The legacy leaderboard evaluates unsupervised methods on the Sintel training
split's Final rendering pass without using Sintel ground-truth flow for
training or fine-tuning.  It is separate from the hidden supervised/general
test-server leaderboard.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_mpi_sintel_final_unsupervised_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import db_manager

TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 85620
SOURCE_TITLE = "A Naturalistic Open Source Movie for Optical Flow Evaluation"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/85620"
HOMEPAGE = "http://sintel.is.tue.mpg.de/"
DATASET_NAME = "MPI Sintel Final Unsupervised"
DATASET_SLUG = "mpi-sintel-final-unsupervised"
METRIC_NAME = "Average End-Point Error"


def main() -> None:
    with db_manager.session_local() as session:
        task = (
            session.execute(
                text("SELECT id, slug FROM tasks WHERE id = :id"), {"id": TASK_ID}
            )
            .mappings()
            .one_or_none()
        )
        if task is None or task["slug"] != TASK_SLUG:
            raise RuntimeError(f"Expected task id={TASK_ID} slug={TASK_SLUG!r}")

        paper = (
            session.execute(
                text("SELECT id, title FROM papers WHERE id = :id"),
                {"id": SOURCE_PAPER_ID},
            )
            .mappings()
            .one_or_none()
        )
        if paper is None or paper["title"] != SOURCE_TITLE:
            raise RuntimeError(
                f"Expected source paper id={SOURCE_PAPER_ID} title={SOURCE_TITLE!r}"
            )

        metric_id = session.execute(
            text(
                """
                INSERT INTO metrics (
                    name, full_name, direction, description, scale
                )
                VALUES (
                    :name, :full_name, 'lower_is_better', :description, 'unbounded'
                )
                ON CONFLICT (name) DO UPDATE SET
                    full_name = COALESCE(metrics.full_name, EXCLUDED.full_name),
                    direction = 'lower_is_better',
                    description = COALESCE(metrics.description, EXCLUDED.description),
                    scale = COALESCE(metrics.scale, EXCLUDED.scale)
                RETURNING id
                """
            ),
            {
                "name": METRIC_NAME,
                "full_name": "Average End-Point Error",
                "description": (
                    "Mean Euclidean distance in pixels between predicted and "
                    "ground-truth optical-flow vectors; lower is better."
                ),
            },
        ).scalar_one()

        dataset_id = session.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    homepage, url, paper_url, introducing_paper_id,
                    introducing_paper_title, introduced_year, split_name
                )
                VALUES (
                    :name, :slug, :full_name, :description, :short_description,
                    :homepage, :url, :paper_url, :paper_id,
                    :paper_title, 2012, 'Training split, Final pass (unsupervised)'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    homepage = EXCLUDED.homepage,
                    url = EXCLUDED.url,
                    paper_url = EXCLUDED.paper_url,
                    introducing_paper_id = EXCLUDED.introducing_paper_id,
                    introducing_paper_title = EXCLUDED.introducing_paper_title,
                    introduced_year = EXCLUDED.introduced_year,
                    split_name = EXCLUDED.split_name
                RETURNING id
                """
            ),
            {
                "name": DATASET_NAME,
                "slug": DATASET_SLUG,
                "full_name": "MPI Sintel Optical Flow — Final Pass, Unsupervised",
                "description": (
                    "Unsupervised optical-flow evaluation on the MPI Sintel "
                    "training split using the Final rendering pass. Ground-truth "
                    "flow is used only to compute Average End-Point Error: eligible "
                    "models do not use Sintel target ground-truth supervision or "
                    "fine-tuning. This follows the legacy source-defined unsupervised "
                    "evaluation convention and is deliberately separate from the "
                    "official hidden Final test-server supervised/general benchmark."
                ),
                "short_description": (
                    "Sintel training split, Final pass, without target GT training."
                ),
                "homepage": HOMEPAGE,
                "url": HOMEPAGE,
                "paper_url": NATIVE_PAPER_URL,
                "paper_id": SOURCE_PAPER_ID,
                "paper_title": SOURCE_TITLE,
            },
        ).scalar_one()

        session.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                VALUES (:task_id, :dataset_id, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    supports_harness = FALSE
                """
            ),
            {"task_id": TASK_ID, "dataset_id": dataset_id},
        )
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "metric_id": metric_id,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": SOURCE_PAPER_ID, "task_id": TASK_ID},
        )

        session.commit()
        print(
            f"Ready: dataset_id={dataset_id} slug={DATASET_SLUG} "
            f"task_id={TASK_ID} metric_id={metric_id} paper_id={SOURCE_PAPER_ID}"
        )


if __name__ == "__main__":
    main()
