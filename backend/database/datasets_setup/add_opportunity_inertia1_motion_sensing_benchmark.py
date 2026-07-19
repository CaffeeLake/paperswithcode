#!/usr/bin/env python3
"""Add the OPPORTUNITY benchmark under the reported Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "opportunity-inertia-1"
PARENT_DATASET_ID = 1230
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = "https://archive.ics.uci.edu/dataset/226/opportunity+activity+recognition"
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
                    'OPPORTUNITY (Inertia-1 Locomotion Protocol)',
                    :slug,
                    'OPPORTUNITY Activity Recognition — Inertia-1 Locomotion '
                    'Protocol',
                    'The reported Inertia-1 OPPORTUNITY task is four-class '
                    'locomotion recognition using the Locomotion annotation '
                    'track: standing, walking, sitting, and lying. It uses '
                    'triaxial accelerometer streams at the left wrist (LWR) '
                    'and right wrist (RWR). The loader treats each wrist/session '
                    'stream as a separate recording and pools their held-out '
                    'window probabilities for dataset-level scoring; the two '
                    'wrists are not concatenated into a six-channel input.',
                    'Four-class OPPORTUNITY locomotion recognition from wrist '
                    'accelerometers under the frozen Inertia-1 protocol.',
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
                    '"Wrist", "Locomotion Recognition"]'::jsonb,
                    'Frozen S1-S4 groups; 30 s/1 s; about 25.6K/12.2K/9.8K train/val/test',
                    'Protocol: rebuild each of the 24 raw S1-S4 ADL/Drill '
                    'session files independently from its explicit millisecond '
                    'timestamps (native rate approximately 30.3 Hz). Split at '
                    'timestamp gaps over one second. The audited rebuild '
                    'extracts 19 on-body streams and all seven annotation '
                    'tracks; for each signal require at least two finite '
                    'samples per axis in every retained segment, interpolate '
                    'missing values in both directions, divide acceleration by '
                    '1000, apply a fourth-order 10 Hz Butterworth low-pass '
                    'filter, and interpolate onto a uniform 20 Hz grid. Align '
                    'every label track by nearest timestamp and map raw '
                    'zero/missing labels to -1. For the reported evaluation, '
                    'select only LWR and RWR triaxial accelerometer streams as '
                    'separate recordings and select only the Locomotion label '
                    'track. Use overlapping 30-second windows (600 samples) '
                    'with a 20-sample/1-second stride. Keep Locomotion IDs 1, '
                    '2, 4, and 5, mapped respectively to stand, walk, sit, and '
                    'lie. Treat -1 as unwanted/null; drop a window when more '
                    'than 50% of its samples are null, then assign the majority '
                    'remaining label. Use the one frozen seed-0 '
                    'group-stratified train/validation/test split; group by '
                    'participant S1-S4 (not session), so all ADL/Drill sessions '
                    'and both wrist streams from a participant stay in one '
                    'split. The generator targets 70%/15%/15%, while the four '
                    'coarse participant groups yield the paper-reported '
                    'approximately 25.6K/12.2K/9.8K train/validation/test '
                    'windows (47,626 audited windows in total). This is one '
                    'fixed split, not the Opportunity Challenge split or '
                    'cross-validation; do not average across folds. On pooled '
                    'held-out test-window probabilities, compute one-vs-rest '
                    'ROC AUC and average equally over the four classes for '
                    'AUROC; compute sklearn average precision one-vs-rest and '
                    'average equally over the classes for AUPRC. Report both '
                    'on the 0-100 percentage scale. Linear-probe and '
                    'full-finetuning results are eligible only when their mode '
                    'is identified. Exclude Task B2 gesture recognition, Task '
                    'B1 spotting, Task C noise robustness, the HL/LL/ML arm or '
                    'object annotation tracks, Null as a scored class, and any '
                    'other label task. Also exclude back/hip/hand/arm/knee '
                    'placements; gyroscope, magnetometer, full on-body inputs, '
                    'single-wrist or concatenated/fused wrists; magnitude or '
                    'uniaxial inputs; altered preprocessing, sampling rates, '
                    'windows, strides, labels, or null thresholds; random '
                    'window/session splits, the canonical B2 split, other '
                    'frozen splits/seeds, participant overlap, or run/fold '
                    'averaging; and Accuracy, F1, micro/weighted AUC, or '
                    '0-1-scaled scores. The paper''s sensor/placement-fusion '
                    'study reports Macro F1 and requires a separate leaderboard.',
                    'https://paperswithcode.com/dataset/opportunity'
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
