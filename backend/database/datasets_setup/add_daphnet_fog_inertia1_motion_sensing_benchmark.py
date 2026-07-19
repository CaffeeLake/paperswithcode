#!/usr/bin/env python3
"""Add Daphnet FoG under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "daphnet-fog-inertia-1"
PARENT_DATASET_ID = 1247
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait"
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
                    'Daphnet FoG (Inertia-1 Protocol)',
                    :slug,
                    'Daphnet FoG — Inertia-1 30-Second Ankle Protocol',
                    'The reported Inertia-1 Daphnet benchmark detects freezing '
                    'of gait from one ankle triaxial accelerometer. It uses '
                    'audited 64-to-20 Hz preprocessing, overlapping 30-second '
                    'windows with a 20% FoG coverage rule, and one frozen '
                    'participant-disjoint split.',
                    'Binary freezing-of-gait detection from ankle '
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
                    '"Ankle", "Freezing of Gait", "Parkinson''s Disease"]'::jsonb,
                    'Frozen subjects; 30 s/1 s; about 12.5K/2.6K/2.8K train/val/test',
                    'Protocol: use all 17 Daphnet SxxRyy recordings. Read each '
                    'whitespace-delimited raw file as timestamp milliseconds, '
                    'ankle/thigh/trunk triaxial accelerations in mg, and raw '
                    'annotation. Drop rows missing any required field, sort by '
                    'timestamp, and deduplicate timestamps. Split each '
                    'recording at timestamp gaps longer than one second. '
                    'Within every contiguous segment, convert acceleration '
                    'from mg to g, apply a fourth-order 10 Hz Butterworth '
                    'low-pass filter with zero-phase filtfilt, then resample '
                    'the three placements from 64 Hz to a uniform 20 Hz '
                    'timeline with polyphase resampling (up 20, down 64), '
                    'cropping or edge-padding only to the exact rebuilt '
                    'timeline length. Align labels to that timeline by nearest '
                    'raw timestamp and concatenate the rebuilt segments in '
                    'recording order. Map raw annotation 0 outside the '
                    'experiment to -1, raw 1 experiment/no-freeze to binary 0, '
                    'and raw 2 freezing to binary 1. Although ankle, thigh, and '
                    'trunk streams are rebuilt, select only ankle '
                    'accelerometer x/y/z for this reported single-stream '
                    'benchmark. Form overlapping 30-second windows (600 '
                    'samples) with a 20-sample/one-second stride. Discard a '
                    'window only when more than 50% of its samples are -1 '
                    'outside-experiment. Label every retained window FoG '
                    '(positive class 1) when at least 20% of all 600 samples '
                    '(at least 120 samples) are FoG; otherwise label it '
                    'non-FoG (class 0) by majority over the non--1 samples. '
                    'The audited rebuild contains 599,342 timesteps and 17,878 '
                    'valid windows: 14,589 non-FoG and 3,289 FoG. Use the one '
                    'frozen seed-0 group-stratified train/validation/test '
                    'split, grouping every run by its base Sxx participant so '
                    'no participant or recording crosses splits. The '
                    'generator targets 70%/15%/15% with 200 randomized greedy '
                    'restarts and yields the paper-reported approximately '
                    '12.5K/2.6K/2.8K windows. This is one fixed split, not '
                    'leave-one-subject-out or cross-validation. On held-out '
                    'test windows having finite two-class probability vectors, '
                    'use the probability of FoG class 1: compute standard '
                    'binary ROC AUC for AUROC and sklearn average precision '
                    'for AUPRC. Both classes must be present. Report both on '
                    'the 0-100 percentage scale. Linear-probe and full-'
                    'finetuning results are eligible only when their mode is '
                    'identified. Exclude the canonical Daphnet 4-second, '
                    'one-second-step, greater-than-50%-FoG LOSO task over '
                    'eight FoG-positive participants; thigh-only, trunk-only, '
                    'three-placement fusion, multi-stream, uniaxial, or '
                    'magnitude inputs; exclusion of non-freezers; '
                    'participant-overlapping splits, LOSO, recording-level '
                    'splits that separate runs from one participant, other '
                    'frozen splits/seeds, cross-validation, or run/fold '
                    'averaging; altered preprocessing, sampling rates, '
                    'windows, strides, outside-experiment filtering, or FoG '
                    'coverage thresholds; and Accuracy, balanced Accuracy, '
                    'F1/Macro F1, event-level/tolerance metrics, 0-1-scaled '
                    'scores, or any AUPRC whose positive class is not FoG.',
                    'https://paperswithcode.com/dataset/daphnet-freezing-of-gait'
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
