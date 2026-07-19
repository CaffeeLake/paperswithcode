#!/usr/bin/env python3
"""Add FoGTurning under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "fogturning-inertia-1"
PARENT_DATASET_ID = 1252
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://doi.org/10.6084/m9.figshare.14984667"
CODE_URL = "https://github.com/yang-ai-lab/Inertia-1"
HERO_URL = "https://yang-ai-lab.github.io/Inertia-1/static/images/wrist-transfer.svg"


def main() -> None:
    db = next(get_database_session())
    try:
        source = db.execute(
            text(
                """
                SELECT title
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

        db.execute(
            text("SELECT id FROM datasets WHERE id = :dataset_id"),
            {"dataset_id": PARENT_DATASET_ID},
        ).scalar_one()

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
        metric_rows = db.execute(
            text(
                """
                SELECT id, name
                FROM metrics
                WHERE name IN ('AUROC', 'AUPRC')
                  AND direction = 'higher_is_better'
                  AND scale = 'percentage'
                """
            )
        ).all()
        metric_ids = {row.name: row.id for row in metric_rows}
        if set(metric_ids) != {"AUROC", "AUPRC"}:
            raise RuntimeError(f"Missing percentage AUC metrics: {metric_ids}")

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
                    'FoGTurning (Inertia-1 Protocol)',
                    :slug,
                    'FoGTurning — Inertia-1 30-Second Shank Protocol',
                    'The reported Inertia-1 FoGTurning benchmark detects '
                    'freezing of gait from one shank triaxial accelerometer. '
                    'It harmonizes the released 128 Hz recordings to 20 Hz, '
                    'uses overlapping 30-second windows with a 20% FoG rule, '
                    'and evaluates one frozen participant-disjoint split.',
                    'Binary freezing-of-gait detection from shank '
                    'accelerometry under the frozen Inertia-1 protocol.',
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
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Shank", "Freezing of Gait", '
                    '"Parkinson''s Disease"]'::jsonb,
                    'Frozen participants; 30 s/1 s; about 4.5K/1.0K/1.0K train/val/test',
                    'Protocol: use all released FoGTurning recordings from '
                    'the 35 participants with Parkinson''s disease, including '
                    'every available session and turning trial. The public '
                    'files provide one Physilog 5 IMU on each participant''s '
                    'most affected shank, sampled at 128 Hz, with triaxial '
                    'accelerometer (g), triaxial gyroscope (degrees/second), '
                    'time, and sample-level freezing labels. The released '
                    'signals have already received the dataset authors'' '
                    'fourth-order zero-phase 60 Hz low-pass filtering. Map '
                    'the consensus sample labels 0 to non-FoG class 0 and 1 '
                    'to FoG class 1; encode any unavailable label as -1. For '
                    'Inertia-1 harmonization, process each recording without '
                    'crossing a participant, session, or trial boundary: '
                    'reject non-finite sensor samples, apply a fourth-order '
                    '10 Hz zero-phase Butterworth anti-alias filter to each '
                    'axis, and resample the uniform 128 Hz sequence to 20 Hz '
                    'with rational polyphase resampling (up 20, down 128), '
                    'aligning the categorical label sequence to the rebuilt '
                    'sample indices. The Inertia-1 processed representation '
                    'keeps accelerometer and gyroscope as separate sibling '
                    'streams with a shared label file, but this reported '
                    'benchmark selects only the shank triaxial accelerometer '
                    'x/y/z stream; do not fuse or substitute gyroscope. Form '
                    'overlapping 30-second windows (600 samples) with a '
                    '20-sample/one-second stride. Discard a window only when '
                    'more than 50% of its samples are -1. Label a retained '
                    'window FoG (positive class 1) when at least 20% of all '
                    '600 samples (at least 120 samples) are FoG; otherwise '
                    'label it non-FoG (class 0) by majority over available '
                    'non--1 samples. Use the one frozen seed-0 group-'
                    'stratified train/validation/test split, grouping all '
                    'sessions and trials by participant so nobody crosses '
                    'splits. The split generator targets 70%/15%/15% and '
                    'chooses among 200 randomized greedy restarts, yielding '
                    'the paper-reported approximately 4.5K/1.0K/1.0K '
                    'windows. This is one fixed participant split, not LOSO '
                    'or cross-validation. On held-out test windows having '
                    'finite two-class probability vectors, use the '
                    'probability of FoG class 1: compute standard binary ROC '
                    'AUC for AUROC and sklearn average precision for AUPRC; '
                    'both classes must be present. Report both metrics on the '
                    '0-100 percentage scale. Linear-probe and full-finetuning '
                    'results are eligible only when their mode is identified. '
                    'Exclude the canonical FoGTurning protocol: 128 Hz '
                    'accelerometer-plus-gyroscope input, two-second/256-sample '
                    'windows, 75% overlap (64-sample/0.5-second stride), '
                    'majority window labels, 35-fold participant LOSO, and '
                    'pooled binary Macro F1 on the 0-1 scale. Also exclude '
                    'gyroscope-only, accelerometer-plus-gyroscope, other '
                    'placements, magnitude or uniaxial inputs; trial-level or '
                    'participant-overlapping splits, LOSO, other frozen '
                    'splits/seeds, cross-validation, or run/fold averaging; '
                    'altered filtering, sampling rates, windows, strides, '
                    'missing-label handling, or FoG coverage thresholds; '
                    'event-level or tolerance scoring; Accuracy, balanced '
                    'Accuracy, F1/Macro F1; 0-1-scaled AUC scores; or any '
                    'AUPRC whose positive class is not FoG.',
                    'https://paperswithcode.com/dataset/fogturning'
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
        for metric_id in metric_ids.values():
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
                "auroc_metric_id": metric_ids["AUROC"],
                "auprc_metric_id": metric_ids["AUPRC"],
                "source_paper_id": SOURCE_PAPER_ID,
                "source_paper_url": native_paper_url,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
