#!/usr/bin/env python3
"""Add RecoFit under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "recofit-inertia-1"
PARENT_DATASET_ID = 1246
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://github.com/microsoft/Exercise-Recognition-from-Wearable-Sensors"
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
                    'RecoFit (Inertia-1 Protocol)',
                    :slug,
                    'RecoFit — Inertia-1 22-Class Right-Arm Exercise Protocol',
                    'The reported Inertia-1 RecoFit benchmark recognizes 22 '
                    'walking, cardio, stretching, core, and resistance '
                    'activities from a right-arm triaxial accelerometer. It '
                    'uses the audited 126-visit RecoFit subset, overlapping '
                    '30-second windows at 20 Hz, and one frozen visit-token-'
                    'disjoint split.',
                    'Twenty-two-class exercise recognition from right-arm '
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
                    '"Right Arm", "Exercise Recognition", '
                    '"Human Activity Recognition"]'::jsonb,
                    'Frozen visit tokens; 30 s/1 s; about 63.1K/13.6K/13.4K train/val/test',
                    'Protocol: start from exercise_data.50.0000_multionly.mat '
                    'and use all 126 audited subject-visit recordings. For '
                    'each visit, retain the paired right-arm accelerometer and '
                    'gyroscope interval common to both sensors, interpolate '
                    'missing axis values, and reconstruct activity labels from '
                    'the annotated start/end intervals. Normalize Tap Left '
                    'Device and Tap Right Device to Tap IMU Device, fill '
                    'unlabeled raw samples from the nearest labeled sample, '
                    'and align labels to the rebuilt timeline by nearest '
                    'timestamp. Estimate each stream rate from the median '
                    'positive timestamp difference, apply a fourth-order 10 Hz '
                    'Butterworth low-pass filter when its effective rate '
                    'exceeds 20 Hz, then resample the nominal 50 Hz signal to '
                    'a uniform 20 Hz grid with polyphase resampling when the '
                    'source rate is within 0.05 Hz of an integer, otherwise '
                    'use per-axis linear interpolation. Although accelerometer '
                    'and gyroscope are rebuilt and time-aligned together, use '
                    'only right-arm accelerometer x/y/z for this reported '
                    'single-stream benchmark. Keep exactly these 22 labels: '
                    'Walk; Static stretch; Running (treadmill); Elliptical '
                    'machine; Static Stretch (at your own pace); Rowing '
                    'machine; Dynamic Stretch (at your own pace); Jump Rope; '
                    'Plank; Butterfly Sit-up; Lunge (alternating both legs, '
                    'weight optional); Wall Squat; Squat (arms in front of '
                    'body, parallel to ground); Burpee; Triceps Kickback (knee '
                    'on bench) (label spans both arms); Two-arm Dumbbell Curl '
                    '(both arms, not alternating); Dumbbell Row (knee on '
                    'bench) (label spans both arms); Sit-up (hands positioned '
                    'behind head); V-up; Sit-ups; Dumbbell Squat (hands at '
                    'side); and Russian Twist. These are the audited exercise '
                    'labels having more than 2,000 valid majority-vote '
                    '30-second windows at 20 Hz with a one-second stride. Map '
                    'Non-Exercise, Device on Table, <Initial Activity>, Invalid, '
                    'Note, Tap IMU Device, Arm Band Adjustment, Repetitive '
                    'Stretching, every other raw exercise label omitted from '
                    'the fixed 22-class encoder, and null/unknown labels to '
                    'unwanted -1. Form overlapping 30-second windows (600 '
                    'samples) with a 20-sample/one-second stride. Drop a window '
                    'only when more than 50% of its samples are unwanted, then '
                    'assign the majority remaining one of the 22 activities. '
                    'Use the one frozen seed-0 group-stratified train/validation/'
                    'test split. Group windows by the parsed sNNNvMMM recording '
                    'token, so no visit crosses splits; this key intentionally '
                    'includes the visit suffix and therefore must not be '
                    'reinterpreted as leave-one-biological-participant-out. '
                    'The generator targets 70%/15%/15% with 200 randomized '
                    'greedy restarts and yields the paper-reported approximately '
                    '63.1K/13.6K/13.4K windows (89,977 valid windows in the '
                    'audited rebuild). This is one fixed split, not leave-one-'
                    'participant-out or cross-validation. On finite held-out '
                    'test-window probabilities, compute one-vs-rest ROC AUC '
                    'separately for every present class and average the 22 '
                    'classes equally for AUROC; compute sklearn one-vs-rest '
                    'average precision per class and average classes equally '
                    'for AUPRC. Report both on the 0-100 percentage scale. '
                    'Linear-probe and full-finetuning results are eligible only '
                    'when their mode is identified. Exclude the canonical '
                    'RecoFit leave-one-participant-out exercise-recognition '
                    'task; any label taxonomy other than the exact 22 classes '
                    'above; gyroscope-only, accelerometer-plus-gyroscope fusion, '
                    'multi-stream, uniaxial, or magnitude inputs; biological-'
                    'participant grouping, participant- or visit-overlapping '
                    'splits, leave-one-participant-out, other frozen splits/'
                    'seeds, cross-validation, or run/fold averaging; altered '
                    'preprocessing, sampling rates, windows, strides, label '
                    'filters, or unwanted thresholds; and Accuracy, F1/Macro '
                    'F1, micro/weighted AUC, or 0-1-scaled scores. The paper''s '
                    'sensor-fusion study reports Macro F1 and requires a '
                    'separate leaderboard.',
                    NULL
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
