"""Add the official KITTI 2012 hidden optical-flow test benchmark.

This leaderboard is deliberately distinct from KITTI 2015, training-split
evaluation, and unsupervised-only protocols.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_kitti_2012_optical_flow_test_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import db_manager

TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 98365
SOURCE_TITLE = "Are we ready for autonomous driving? The KITTI vision benchmark suite"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/98365"
HOMEPAGE = "https://www.cvlibs.net/datasets/kitti/eval_stereo_flow.php?benchmark=flow"
DATASET_NAME = "KITTI 2012 Optical Flow Test"
DATASET_SLUG = "kitti-2012-optical-flow-test"

METRICS = {
    "Average End-Point Error": {
        "full_name": "Average End-Point Error",
        "description": (
            "Mean Euclidean distance in pixels between predicted and ground-truth "
            "optical-flow vectors; lower is better."
        ),
        "scale": "unbounded",
    },
    "Out-Noc": {
        "full_name": "Outlier Percentage on Non-Occluded Pixels",
        "description": (
            "Percentage of non-occluded KITTI 2012 test pixels whose optical-flow "
            "endpoint error exceeds the official outlier threshold; lower is better."
        ),
        "scale": "0-100",
    },
}


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

        metric_ids = {}
        for name, spec in METRICS.items():
            metric_ids[name] = session.execute(
                text(
                    """
                    INSERT INTO metrics (
                        name, full_name, direction, description, scale
                    )
                    VALUES (
                        :name, :full_name, 'lower_is_better', :description, :scale
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        full_name = COALESCE(metrics.full_name, EXCLUDED.full_name),
                        direction = 'lower_is_better',
                        description = COALESCE(metrics.description, EXCLUDED.description),
                        scale = COALESCE(metrics.scale, EXCLUDED.scale)
                    RETURNING id
                    """
                ),
                {"name": name, **spec},
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
                    :paper_title, 2012, 'Official hidden test set'
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
                "full_name": "KITTI 2012 Optical Flow — Official Test Set",
                "description": (
                    "Official KITTI 2012 optical-flow benchmark evaluated on the "
                    "hidden test set through the KITTI server. The primary metric is "
                    "Average End-Point Error; Out-Noc separately reports the outlier "
                    "percentage over non-occluded pixels. This general test protocol "
                    "must not be mixed with KITTI 2015, KITTI 2012 training-split "
                    "results, or unsupervised-only leaderboards."
                ),
                "short_description": (
                    "Official hidden KITTI 2012 optical-flow test-server protocol."
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
        for metric_id in metric_ids.values():
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
            f"task_id={TASK_ID} metrics={metric_ids} paper_id={SOURCE_PAPER_ID}"
        )


if __name__ == "__main__":
    main()
