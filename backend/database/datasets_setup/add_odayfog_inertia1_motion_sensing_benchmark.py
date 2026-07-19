#!/usr/bin/env python3
"""Add OdayFoG under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "odayfog-inertia-1"
PARENT_DATASET_ID = 1249
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://github.com/stanfordnmbl/imu-fog-detection"
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
                    'OdayFoG (Inertia-1 Protocol)',
                    :slug,
                    'OdayFoG — Inertia-1 30-Second Left-Ankle Protocol',
                    'The reported Inertia-1 OdayFoG benchmark detects freezing '
                    'of gait from one left-ankle triaxial accelerometer. It '
                    'uses audited 128-to-20 Hz preprocessing, overlapping '
                    '30-second windows with a 20% FoG coverage rule, and one '
                    'frozen participant-disjoint split.',
                    'Binary freezing-of-gait detection from left-ankle '
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
                    '"Left Ankle", "Freezing of Gait", '
                    '"Parkinson''s Disease"]'::jsonb,
                    'Frozen participants; 30 s/1 s; about 1.7K/0.8K/0.8K train/val/test',
                    'Protocol: use the 59 audited OdayFoG walk-trial '
                    'recordings across seven participants. Raw recordings are '
                    'Excel workbooks with a time column, freeze_label, and '
                    'available triaxial accelerometer/gyroscope streams from '
                    'head, chest, lumbar, bilateral wrists, thighs, ankles, '
                    'and feet. When one recording appears in both the '
                    'imus6_subjects7 and imus11_subjects4 releases, prefer the '
                    'richer imus11_subjects4 copy. Preserve the processed '
                    'naming that omits the raw walklr token; for the one '
                    'collided subject7_v12_t2 identifier, retain only the '
                    'walklr branch whose rebuilt target length matches the '
                    'existing shared label artifact and drop the unmatched '
                    'branch. Never synthesize missing sensor placeholders: '
                    'write only streams actually present in each workbook. '
                    'For each selected recording, discard invalid timestamps, '
                    'sort stably by time, and deduplicate timestamps. For '
                    'every sensor stream, remove rows missing any of x/y/z and '
                    'require a single contiguous segment with no internal gap '
                    'longer than one second. Restrict all available streams to '
                    'their common temporal overlap. Estimate each source rate '
                    'as (sample count minus one) divided by its timestamp '
                    'span; when it exceeds 20 Hz (nominally 128 Hz), apply a '
                    'fourth-order 10 Hz Butterworth low-pass filter with zero-'
                    'phase filtfilt. Rebuild a uniform common 20 Hz timeline '
                    'using linear interpolation independently for x/y/z, and '
                    'align freeze_label by nearest raw timestamp. Map raw '
                    'freeze_label 0 to non-FoG class 0, 1 to FoG class 1, and '
                    'missing labels to -1. The audited rebuild retains 59 '
                    'shared label files and about 910 real signal files after '
                    'removing fake placeholders and the unmatched collided '
                    'branch. Although every available stream is rebuilt, '
                    'select only ankle_l accelerometer x/y/z for this reported '
                    'single-stream benchmark. Form overlapping 30-second '
                    'windows (600 samples) with a 20-sample/one-second stride. '
                    'Discard a window only when more than 50% of its samples '
                    'are -1. Label every retained window FoG (positive class '
                    '1) when at least 20% of all 600 samples (at least 120 '
                    'samples) are FoG; otherwise label it non-FoG (class 0) by '
                    'majority over non--1 samples. The audited setup yields '
                    '3,332 valid windows. Use the one frozen seed-0 group-'
                    'stratified train/validation/test split, grouping every '
                    'visit/trial by its parsed subjectN participant identifier '
                    'so no participant crosses splits. The generator targets '
                    '70%/15%/15% with 200 randomized greedy restarts and yields '
                    'the paper-reported approximately 1.7K/0.8K/0.8K windows. '
                    'This is one fixed split, not LOSO or cross-validation. On '
                    'held-out test windows having finite two-class probability '
                    'vectors, use the probability of FoG class 1: compute '
                    'standard binary ROC AUC for AUROC and sklearn average '
                    'precision for AUPRC. Both classes must be present. Report '
                    'both on the 0-100 percentage scale. Linear-probe and full-'
                    'finetuning results are eligible only when their mode is '
                    'identified. Exclude the canonical OdayFoG 64 Hz, '
                    'two-second, 50%-overlap, majority-label seven-fold LOSO '
                    'task using lumbar plus bilateral ankle accelerometer and '
                    'gyroscope; the four-participant 11-IMU-only subset; '
                    'ankle_r, lumbar, any other placement, gyroscope-only, '
                    'accelerometer-plus-gyroscope, three-IMU, multi-stream, '
                    'uniaxial, or magnitude inputs; gait-initiation episodes '
                    'or other medication/DBS/assistive-device cohorts; '
                    'participant-overlapping or trial-level splits, LOSO, '
                    'other frozen splits/seeds, cross-validation, or run/fold '
                    'averaging; altered preprocessing, sampling rates, '
                    'windows, strides, missing-label filtering, or FoG '
                    'coverage thresholds; and Accuracy, balanced Accuracy, '
                    'F1/Macro F1, event-level/tolerance metrics, 0-1-scaled '
                    'scores, or any AUPRC whose positive class is not FoG.',
                    'https://paperswithcode.com/dataset/odayfog'
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
