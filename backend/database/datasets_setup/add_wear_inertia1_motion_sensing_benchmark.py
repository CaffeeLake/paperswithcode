#!/usr/bin/env python3
"""Add WEAR under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "wear-inertia-1"
PARENT_DATASET_ID = 1244
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://mariusbock.github.io/wear/"
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
                    'WEAR (Inertia-1 Protocol)',
                    :slug,
                    'WEAR — Inertia-1 18-Class Right-Arm Accelerometer Protocol',
                    'The reported Inertia-1 WEAR benchmark recognizes 18 '
                    'fine-grained workout activities from one right-arm '
                    'triaxial accelerometer. It uses the audited 24-subject '
                    'WEAR subset, overlapping 30-second windows at 20 Hz, and '
                    'one frozen participant-disjoint split.',
                    'Eighteen-class workout recognition from right-arm '
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
                    'Frozen subjects; 30 s/1 s; about 29.0K/6.7K/6.5K train/val/test',
                    'Protocol: use the full audited 24-subject WEAR processed '
                    'subset. The source recordings are synchronized triaxial '
                    'accelerometers from left arm, right arm, left leg, and '
                    'right leg on an implicit regular 50 Hz timeline. Consume '
                    'the audited 20 Hz signal and shared-label parquet '
                    'artifacts as released by the Inertia-1 preprocessing '
                    'contract; the audit selected Step none, so do not '
                    'independently refilter, interpolate, or rebuild those '
                    'artifacts. The audit retained 95 of 96 signal files and '
                    'all 24 shared label files, dropping '
                    'WEAR_S10_left_arm_acc_20Hz_3985.00s.parquet because the '
                    'raw sbj_10 left-arm stream contains a long contiguous NaN '
                    'outage. That corrupted file is outside the selected '
                    'right-arm stream but remains an explicit global '
                    'exclusion. For this reported single-stream benchmark, '
                    'select only right_arm accelerometer x/y/z; do not fuse '
                    'the other arm or either leg. Keep exactly these 18 '
                    'labels: bench-dips; burpees; jogging; jogging (butt-kicks); '
                    'jogging (rotating arms); jogging (sidesteps); jogging '
                    '(skipping); lunges; lunges (complex); push-ups; push-ups '
                    '(complex); sit-ups; sit-ups (complex); stretching '
                    '(hamstrings); stretching (lumbar rotation); stretching '
                    '(lunging); stretching (shoulders); and stretching '
                    '(triceps). Map missing/unlabeled nan rows and any '
                    'null/unknown label to unwanted -1; there is no retained '
                    'background class. Form overlapping 30-second windows '
                    '(600 samples) with a 20-sample/one-second stride. Drop a '
                    'window only when more than 50% of its samples are '
                    'unwanted, then assign the majority remaining one of the '
                    '18 activities. Use the one frozen seed-0 group-stratified '
                    'train/validation/test split, grouping every window by its '
                    'parsed S-prefixed subject identifier so no participant '
                    'crosses splits. The generator targets 70%/15%/15% with '
                    '200 randomized greedy restarts and yields the paper-'
                    'reported approximately 29.0K/6.7K/6.5K windows (42,294 '
                    'valid windows total). This is one fixed split, not LOSO '
                    'or cross-validation. On finite held-out test-window '
                    'probabilities, compute one-vs-rest ROC AUC separately for '
                    'every present class and average the 18 classes equally '
                    'for AUROC; compute sklearn one-vs-rest average precision '
                    'per class and average classes equally for AUPRC. Report '
                    'both on the 0-100 percentage scale. Linear-probe and full-'
                    'finetuning results are eligible only when their mode is '
                    'identified. Exclude the canonical WEAR four-IMU LOSO '
                    'task and its explicit Null/background class; any label '
                    'taxonomy other than the exact 18 classes above; left-arm, '
                    'left-leg, right-leg, four-placement fusion, multi-stream, '
                    'uniaxial, or magnitude inputs; participant-overlapping '
                    'splits, LOSO, other frozen splits/seeds, cross-validation, '
                    'or run/fold averaging; altered preprocessing, sampling '
                    'rates, windows, strides, label filters, or unwanted '
                    'thresholds; and Accuracy, F1/Macro F1, mAP, micro/weighted '
                    'AUC, or 0-1-scaled scores. The official WEAR continuous '
                    'activity-localization and four-sensor recognition '
                    'protocols require separate leaderboards.',
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
