#!/usr/bin/env python3
"""Add the HHAR benchmark under the reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "hhar-inertia-1"
PARENT_DATASET_ID = 1235
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://archive.ics.uci.edu/dataset/344/heterogeneity+activity+recognition"
CODE_URL = "https://github.com/yang-ai-lab/Inertia-1"
HERO_URL = "https://yang-ai-lab.github.io/Inertia-1/static/images/wrist-transfer.svg"


def main() -> None:
    db = next(get_database_session())
    try:
        source = db.execute(
            text(
                """
                SELECT id, title
                FROM papers
                WHERE id = :paper_id
                  AND arxiv_id = :arxiv_id
                  AND is_latest_version
                """
            ),
            {"paper_id": SOURCE_PAPER_ID, "arxiv_id": ARXIV_ID},
        ).one()
        if source.title != SOURCE_TITLE:
            raise RuntimeError(
                f"Unexpected source title for paper {SOURCE_PAPER_ID}: {source.title}"
            )

        native_paper_url = f"https://paperswithcode.co/paper/{ARXIV_ID}"
        db.execute(
            text(
                """
                UPDATE papers
                SET thumbnail_url = :hero_url,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :paper_id
                """
            ),
            {"hero_url": HERO_URL, "paper_id": SOURCE_PAPER_ID},
        )

        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).scalar_one()
        auroc_metric_id = db.execute(
            text(
                """
                SELECT id
                FROM metrics
                WHERE name = 'AUROC'
                  AND direction = 'higher_is_better'
                  AND scale = 'percentage'
                """
            )
        ).scalar_one()
        auprc_metric_id = db.execute(
            text(
                """
                INSERT INTO metrics (
                    name, full_name, direction, scale, description
                )
                VALUES (
                    'AUPRC',
                    'Area Under the Precision-Recall Curve',
                    'higher_is_better',
                    'percentage',
                    'Area under the precision-recall curve, reported as a '
                    'percentage. Multiclass aggregation must be defined by '
                    'the benchmark protocol.'
                )
                ON CONFLICT (name) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    direction = EXCLUDED.direction,
                    scale = EXCLUDED.scale,
                    description = EXCLUDED.description,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
            )
        ).scalar_one()

        dataset_id = db.execute(
            text(
                """
                INSERT INTO datasets (
                    name, slug, full_name, description, short_description,
                    url, homepage, parent_dataset_id, variant_type,
                    image_url, thumbnail_url, verified_image_url,
                    introducing_paper_id, introducing_paper_title, paper_url,
                    introduced_date, introduced_year, modalities, split_name,
                    warning, pwc_url
                )
                VALUES (
                    'HHAR (Inertia-1 Protocol)',
                    :slug,
                    'Heterogeneity Human Activity Recognition Dataset — '
                    'Inertia-1 Protocol',
                    'The Inertia-1 HHAR protocol recognizes six activities: '
                    'standing, sitting, walking downstairs, walking upstairs, '
                    'cycling, and walking. It uses only the triaxial '
                    'accelerometer from smartwatches. The audited preprocessing '
                    'retains user-device recordings with overlapping watch '
                    'accelerometer and gyroscope timelines, but the reported '
                    'AUROC/AUPRC evaluation consumes the accelerometer stream '
                    'only. Each recording is split at timestamp gaps over one '
                    'second, low-pass filtered at 10 Hz when its effective rate '
                    'exceeds 20 Hz, interpolated to 20 Hz, and aligned to the '
                    'nearest raw activity label.',
                    'Six-class HHAR smartwatch accelerometry under the frozen '
                    'Inertia-1 evaluation protocol.',
                    :data_url,
                    :code_url,
                    :parent_dataset_id,
                    'variant',
                    :hero_url,
                    :hero_url,
                    :hero_url,
                    :paper_id,
                    :paper_title,
                    :paper_url,
                    DATE '2026-07-07',
                    2026,
                    '["Time Series", "Smartwatch", "Accelerometer", '
                    '"Human Activity Recognition"]'::jsonb,
                    'Frozen 70/15/15 User-Device groups; 30 s windows at 1 s stride',
                    'Protocol: use the wrist-worn triaxial accelerometer only. '
                    'After the audited gap-aware preprocessing, use 20 Hz '
                    'signals and overlapping 30-second windows (600 samples) '
                    'with a 20-sample/1-second stride. Map labels exactly as '
                    'stand, sit, stairsdown, stairsup, bike, and walk; map '
                    'null/transition samples to -1. Drop a window when more '
                    'than 50% of its samples are -1, then assign the majority '
                    'of its remaining labels. Use the single frozen '
                    'group-stratified split generated with seed 0 and target '
                    'fractions 70% train, 15% validation, and 15% test (the '
                    'paper reports approximately 10.4K/2.2K/2.2K windows). '
                    'The repository groups by its parsed subject_id; for the '
                    'audited HHAR filenames this is the User-Device recording '
                    'key. This is one fixed split, not cross-validation; do not '
                    'average across folds. For the six-class test probabilities, '
                    'compute one-vs-rest ROC AUC and average equally across '
                    'classes for AUROC; compute sklearn average precision '
                    'one-vs-rest and average equally across classes for AUPRC. '
                    'Report both on the 0-100 percentage scale. Linear-probe '
                    'and full-finetuning results are eligible only when their '
                    'training mode is identified. Exclude phones, gyroscope, '
                    'ACC+GYR fusion, other placements, magnitude/uniaxial input, '
                    'non-20-Hz signals, other window sizes or strides, random '
                    'window splits, different frozen splits or seeds, LOUO, '
                    'label merges/subsets, accuracy/F1 results, micro/weighted '
                    'AUC aggregation, 0-1-scaled scores, and averaging across '
                    'runs or folds. In particular, the paper''s ACC+GYR '
                    'multi-stream sensor-fusion study reports Macro F1 and '
                    'requires a separate leaderboard.',
                    'https://paperswithcode.com/dataset/hhar'
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    url = EXCLUDED.url,
                    homepage = EXCLUDED.homepage,
                    parent_dataset_id = EXCLUDED.parent_dataset_id,
                    variant_type = EXCLUDED.variant_type,
                    image_url = EXCLUDED.image_url,
                    thumbnail_url = EXCLUDED.thumbnail_url,
                    verified_image_url = EXCLUDED.verified_image_url,
                    introducing_paper_id = EXCLUDED.introducing_paper_id,
                    introducing_paper_title = EXCLUDED.introducing_paper_title,
                    paper_url = EXCLUDED.paper_url,
                    introduced_date = EXCLUDED.introduced_date,
                    introduced_year = EXCLUDED.introduced_year,
                    modalities = EXCLUDED.modalities,
                    split_name = EXCLUDED.split_name,
                    warning = EXCLUDED.warning,
                    pwc_url = EXCLUDED.pwc_url,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
            ),
            {
                "slug": DATASET_SLUG,
                "data_url": DATA_URL,
                "code_url": CODE_URL,
                "parent_dataset_id": PARENT_DATASET_ID,
                "hero_url": HERO_URL,
                "paper_id": SOURCE_PAPER_ID,
                "paper_title": SOURCE_TITLE,
                "paper_url": native_paper_url,
            },
        ).scalar_one()

        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": SOURCE_PAPER_ID, "task_id": task_id},
        )
        db.execute(
            text(
                """
                INSERT INTO task_datasets (
                    task_id, dataset_id, featured_rank, supports_harness
                )
                VALUES (:task_id, :dataset_id, NULL, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                    featured_rank = NULL,
                    supports_harness = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id},
        )
        for metric_id in (auroc_metric_id, auprc_metric_id):
            db.execute(
                text(
                    """
                    INSERT INTO task_dataset_metrics (
                        task_id, dataset_id, metric_id
                    )
                    VALUES (:task_id, :dataset_id, :metric_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "task_id": task_id,
                    "dataset_id": dataset_id,
                    "metric_id": metric_id,
                },
            )

        db.commit()
        print(
            {
                "dataset_id": dataset_id,
                "dataset_slug": DATASET_SLUG,
                "parent_dataset_id": PARENT_DATASET_ID,
                "task_id": task_id,
                "auroc_metric_id": auroc_metric_id,
                "auprc_metric_id": auprc_metric_id,
                "source_paper_id": SOURCE_PAPER_ID,
                "source_paper_url": native_paper_url,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
