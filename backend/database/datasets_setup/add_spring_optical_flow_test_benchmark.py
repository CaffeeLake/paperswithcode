#!/usr/bin/env python3
"""Add the official Spring hidden-test optical-flow leaderboard.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_spring_optical_flow_test_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import get_engine


TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 98607
DATASET_SLUG = "spring-optical-flow-test"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/98607"

METRICS = {
    "1px total": {
        "full_name": "1-Pixel Error Rate (Total)",
        "scale": "percentage",
        "description": (
            "Percentage of all evaluated optical-flow pixels whose end-point error "
            "exceeds one pixel on the official Spring test server."
        ),
    },
    "EPE": {
        "full_name": "End-Point Error",
        "scale": "unbounded",
        "description": (
            "Mean Euclidean distance in pixels between predicted and ground-truth "
            "optical-flow vectors."
        ),
    },
    "Fl": {
        "full_name": "Optical Flow Outlier Rate",
        "scale": "percentage",
        "description": (
            "Percentage of optical-flow outliers under the benchmark's official Fl "
            "criterion on the Spring hidden test server."
        ),
    },
}


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
                    homepage, variant_type, split_name, introducing_paper_id,
                    introducing_paper_title, paper_url, introduced_year,
                    modalities, warning
                )
                VALUES (
                    'Spring Optical Flow Test', :slug,
                    'Spring Optical Flow — Official Hidden Test Set',
                    'The official hidden-test optical-flow leaderboard for the Spring '
                    'high-resolution, high-detail benchmark. Predictions are submitted '
                    'to the Spring evaluation server and evaluated against withheld '
                    'super-resolved UHD ground truth using the benchmark-native total '
                    '1-pixel error rate, end-point error, and Fl outlier rate.',
                    'Official high-resolution Spring hidden-test optical-flow benchmark.',
                    'https://spring-benchmark.org/', 'split',
                    'Optical flow — official hidden test', :paper_id, :paper_title,
                    :paper_url, 2023,
                    CAST('["Images", "Video", "Optical Flow"]' AS jsonb),
                    'Only scores from the official Spring optical-flow hidden test '
                    'server are comparable. Do not mix training-set scores, scene-flow '
                    'or stereo results, or RobustSpring corruption-delta metrics into '
                    'this leaderboard.'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    homepage = EXCLUDED.homepage,
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
                "paper_id": SOURCE_PAPER_ID,
                "paper_title": paper["title"],
                "paper_url": NATIVE_PAPER_URL,
            },
        ).scalar_one()

        metric_ids: dict[str, int] = {}
        for name, spec in METRICS.items():
            metric_ids[name] = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO metrics (
                            name, full_name, direction, scale, description
                        )
                        VALUES (
                            :name, :full_name, 'lower_is_better', :scale, :description
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
                    {"name": name, **spec},
                ).scalar_one()
            )

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
        for metric_id in metric_ids.values():
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
        f"metrics={metric_ids}"
    )


if __name__ == "__main__":
    main()
