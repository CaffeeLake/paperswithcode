#!/usr/bin/env python3
"""Add CAPTURE-24 under the exact reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "capture-24-inertia-1"
PARENT_DATASET_ID = 1236
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://doi.org/10.5287/bodleian:NGx0JOMP5"
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
                    'CAPTURE-24 (Inertia-1 Protocol)',
                    :slug,
                    'CAPTURE-24 — Inertia-1 30-Second Willetts Protocol',
                    'The reported Inertia-1 CAPTURE-24 benchmark classifies '
                    'free-living dominant-wrist triaxial accelerometry from '
                    '151 participants into the ten Willetts activity classes: '
                    'sleep, sitting, standing, walking, vehicle, bicycling, '
                    'sports, manual work, household chores, and mixed activity. '
                    'It uses the paper''s frozen participant-grouped split and '
                    'non-overlapping 30-second windows at the common Inertia-1 '
                    '20 Hz evaluation rate.',
                    'Ten-class free-living dominant-wrist activity recognition '
                    'under the frozen Inertia-1 protocol.',
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
                    '"Dominant Wrist", "Free-Living", '
                    '"Human Activity Recognition"]'::jsonb,
                    'Frozen participants; non-overlapping 30 s; about 214.8K/46.9K/45.8K train/val/test',
                    'Protocol: use the public CAPTURE-24 release with one '
                    'dominant-hand Axivity AX3 triaxial accelerometer recording '
                    'per participant P001 through P151. Use only acceleration '
                    'axes x/y/z in gravity units; exclude camera imagery, diary '
                    'features, demographics, and every derived non-motion '
                    'feature. Convert the release''s fine-grained Compendium of '
                    'Physical Activities annotations using its '
                    'label:Willetts2018 mapping to exactly ten labels, encoded '
                    'as sleep, sitting, standing, walking, vehicle, bicycling, '
                    'sports, manual-work, household-chores, and mixed-activity. '
                    'Do not use the Walmsley four-intensity mapping or the '
                    'older five-category mapping. Consume the triaxial signal '
                    'and dense mapped labels in the canonical 20 Hz Inertia-1 '
                    'layout; axes are linearly interpolated when resampling to '
                    'the requested rate and categorical labels are aligned by '
                    'nearest sample. Under the reported default, form '
                    'non-overlapping 30-second windows of 600 samples: '
                    'CAPTURE-24 explicitly forces non-overlap even though the '
                    'shared evaluation command requests overlap, so the stride '
                    'is 600 samples/30 seconds, not 20 samples/one second. Map '
                    'blank annotations to unwanted/null; keep a window when at '
                    'most 50% of its samples are blank, then assign the majority '
                    'among its ten nonblank Willetts labels. Use the one frozen '
                    'seed-0 group-stratified 70%/15%/15% '
                    'train/validation/test split with 200 randomized greedy '
                    'restarts, grouping all windows by P001-through-P151 '
                    'participant ID so no person crosses splits. The paper '
                    'reports approximately 214.8K/46.9K/45.8K windows. This is '
                    'not the canonical P001-P100 derivation/P101-P151 test '
                    'split, LOSO, or cross-validation. Do not cap or subsample '
                    'windows or classes. On finite held-out test-window '
                    'probabilities, compute one-vs-rest ROC AUC per present '
                    'class and average the ten classes equally for AUROC; '
                    'compute sklearn one-vs-rest average precision per class '
                    'and average classes equally for AUPRC. Report both on the '
                    '0-100 percentage scale. Linear-probe and full-finetuning '
                    'results are eligible only when their mode is identified. '
                    'Exclude 10-second windows; overlapping or one-second-stride '
                    'windows; the official fixed P001-P100/P101-P151 split; '
                    'random-window, participant-overlapping, LOSO, alternate '
                    'seed, cross-validation, or run/fold-averaged results; '
                    'four-class physical-activity-intensity, five-category, '
                    'fine-grained CPA, or other label mappings; non-wrist, '
                    'nondominant-wrist, uniaxial, magnitude, camera, diary, '
                    'metadata, or multimodal inputs; altered preprocessing, '
                    'sampling rates, blank thresholds, capping, or subsampling; '
                    'and Accuracy, F1/Macro F1, micro/weighted AUC, or '
                    '0-1-scaled scores.',
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
