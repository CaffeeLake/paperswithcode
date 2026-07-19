#!/usr/bin/env python3
"""Add the official RobustSpring optical-flow corruption leaderboard.

Run with:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_robustspring_optical_flow_benchmark.py
"""

from sqlalchemy import text

from backend.database.connection import get_engine


TASK_ID = 323
TASK_SLUG = "optical-flow"
SOURCE_PAPER_ID = 48723
SOURCE_ARXIV_ID = "2505.09368"
DATASET_SLUG = "robustspring-optical-flow"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/2505.09368"
HOMEPAGE = (
    "https://spring-benchmark.org/opticalflow?display=robustness&s=robust_Fl_total"
)

METRICS = {
    "robust ΔEPE": {
        "full_name": "RobustSpring Mean Corruption Endpoint Difference",
        "scale": "pixels",
        "description": (
            "Arithmetic mean across RobustSpring's 20 corruptions of the mean "
            "Euclidean endpoint difference, in pixels, between optical-flow "
            "predictions for each clean Spring image and its corresponding "
            "corrupted image. This is a prediction-stability metric, not error "
            "against ground-truth flow."
        ),
    },
    "robust ΔFl": {
        "full_name": "RobustSpring Mean Corruption Fl Difference Rate",
        "scale": "percentage",
        "description": (
            "Arithmetic mean across RobustSpring's 20 corruptions of the "
            "percentage of pixels classified as outliers by the official Fl "
            "criterion when clean-image optical-flow predictions are the "
            "reference and corresponding corrupted-image predictions are the "
            "estimate. This is a prediction-stability rate, not clean Spring Fl."
        ),
    },
    "robust Δ1px": {
        "full_name": "RobustSpring Mean Corruption 1-Pixel Difference Rate",
        "scale": "percentage",
        "description": (
            "Arithmetic mean across RobustSpring's 20 corruptions of the "
            "percentage of pixels whose optical-flow predictions differ by more "
            "than one pixel between each clean Spring image and its corresponding "
            "corrupted image. This is a prediction-stability rate, not clean "
            "Spring 1-pixel error."
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
                text(
                    """
                SELECT id, arxiv_id, title
                FROM papers
                WHERE id = :id AND is_latest_version
                """
                ),
                {"id": SOURCE_PAPER_ID},
            )
            .mappings()
            .one()
        )
        if paper["arxiv_id"] != SOURCE_ARXIV_ID:
            raise RuntimeError(
                f"Source paper {SOURCE_PAPER_ID} is {paper['arxiv_id']!r}, "
                f"not {SOURCE_ARXIV_ID!r}"
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
                    'RobustSpring Optical Flow', :slug,
                    'RobustSpring Optical Flow — Corruption Robustness',
                    'The official RobustSpring optical-flow corruption-robustness '
                    'leaderboard. It applies 20 realistic, time-consistent image '
                    'corruptions at one calibrated severity to the Spring test '
                    'images. The aggregate metrics average the difference between '
                    'a model''s predictions on corresponding clean and corrupted '
                    'images, measuring prediction stability independently of '
                    'ground-truth accuracy.',
                    'Official optical-flow prediction-stability evaluation over 20 RobustSpring corruptions.',
                    :homepage, 'augmented',
                    'Spring test images — 20 corruptions, one severity each',
                    :paper_id, :paper_title, :paper_url, 2025,
                    CAST('["Images", "Video", "Optical Flow", "Image Corruptions"]' AS jsonb),
                    'This leaderboard is distinct from the clean Spring accuracy '
                    'benchmark. Only the official aggregate optical-flow corruption '
                    'metrics robust ΔEPE, robust ΔFl, and robust Δ1px belong here. '
                    'Do not add clean EPE, Fl, or 1px scores, per-corruption scores, '
                    'or RobustSpring scene-flow or stereo results.'
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
                "homepage": HOMEPAGE,
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
                INSERT INTO task_datasets (
                    task_id, dataset_id, featured_rank, supports_harness
                )
                VALUES (:task_id, :dataset_id, NULL, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    featured_rank = NULL,
                    supports_harness = FALSE,
                    updated_at = NOW()
                """
            ),
            {"task_id": TASK_ID, "dataset_id": dataset_id},
        )

        connection.execute(
            text(
                """
                DELETE FROM task_dataset_metrics
                WHERE task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND metric_id != ALL(:metric_ids)
                """
            ),
            {
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "metric_ids": list(metric_ids.values()),
            },
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
