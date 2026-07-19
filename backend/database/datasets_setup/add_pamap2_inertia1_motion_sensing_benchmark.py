#!/usr/bin/env python3
"""Add the PAMAP2 benchmark under the reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "pamap2-inertia-1"
PARENT_DATASET_ID = 1228
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring"
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
                    'PAMAP2 (Inertia-1 Protocol)',
                    :slug,
                    'PAMAP2 Physical Activity Monitoring Dataset — '
                    'Inertia-1 Protocol',
                    'The reported Inertia-1 PAMAP2 protocol recognizes 12 '
                    'activities: lying, sitting, standing, walking, running, '
                    'cycling, Nordic walking, ascending stairs, descending '
                    'stairs, vacuum cleaning, ironing, and rope jumping. It '
                    'uses the hand placement and the two triaxial accelerometer '
                    'streams (acc1 and acc2). The loader treats acc1 and acc2 '
                    'as separate recordings whose test-window predictions are '
                    'pooled for dataset-level scoring; it does not concatenate '
                    'them into a six-channel input.',
                    'Twelve-class PAMAP2 hand accelerometry under the frozen '
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
                    '["Time Series", "Wearable Sensors", "Accelerometer", '
                    '"Hand", "Human Activity Recognition"]'::jsonb,
                    'Frozen subject train/val/test; 30 s/1 s; 16.0K/9.4K/13.5K windows',
                    'Protocol: rebuild each of the nine raw subject recordings '
                    'independently. Split at timestamp gaps over one second; '
                    'within each segment trim to the maximum common overlap of '
                    'all 12 in-scope streams (hand/chest/ankle crossed with '
                    'acc1/acc2/gyroscope/magnetometer), interpolate missing '
                    'axis values, apply a fourth-order 10 Hz Butterworth '
                    'low-pass filter when the effective rate exceeds 20 Hz, '
                    'resample from the native 100 Hz to 20 Hz, and align labels '
                    'by nearest timestamp. For evaluation, select only hand '
                    'acc1 and hand acc2 as separate triaxial accelerometer '
                    'recordings. Use overlapping 30-second windows (600 '
                    'samples) with a 20-sample/1-second stride. Keep exactly '
                    'raw activity IDs 1, 2, 3, 4, 5, 6, 7, 12, 13, 16, 17, '
                    'and 24, mapped respectively to lying, sitting, standing, '
                    'walking, running, cycling, Nordic walking, ascending '
                    'stairs, descending stairs, vacuum cleaning, ironing, and '
                    'rope jumping. Map raw ID 0 to unwanted/null; drop a window '
                    'when more than 50% of its samples are null, then assign '
                    'the majority remaining label. Use the one frozen '
                    'seed-0 group-stratified train/validation/test split; the '
                    'group key is the raw subject ID, so neither accelerometer '
                    'stream from a subject crosses splits. The split generator '
                    'targets 70%/15%/15%, but the nine coarse subject groups '
                    'produce the paper-reported approximately '
                    '16.0K/9.4K/13.5K train/validation/test windows. This is '
                    'one fixed split, not LOSO or cross-validation; do not '
                    'average across folds. On pooled held-out test-window '
                    'probabilities from both hand accelerometer ranges, compute '
                    'one-vs-rest ROC AUC and average equally over the 12 classes '
                    'for AUROC; compute sklearn average precision one-vs-rest '
                    'and average equally over the classes for AUPRC. Report '
                    'both on the 0-100 percentage scale. Linear-probe and '
                    'full-finetuning results are eligible only when their mode '
                    'is identified. Exclude chest or ankle placements; '
                    'gyroscope, magnetometer, heart rate, temperature, or '
                    'orientation; acc1-only, acc2-only, concatenated acc1+acc2, '
                    'and other sensor/placement fusion results; magnitude or '
                    'uniaxial inputs; altered preprocessing, sampling rates, '
                    'windows, strides, label sets, or null thresholds; random '
                    'window splits, LOSO, other frozen splits/seeds, and '
                    'subject overlap; accuracy/F1, micro/weighted AUC, '
                    '0-1-scaled scores, and run/fold averaging. The paper''s '
                    'multi-stream sensor/placement-fusion Macro-F1 study '
                    'requires a separate leaderboard.',
                    'https://paperswithcode.com/dataset/pamap2'
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
