#!/usr/bin/env python3
"""Add the later WISDM smartwatch benchmark under the Inertia-1 protocol."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"
DATASET_SLUG = "wisdm-inertia-1"
PARENT_DATASET_ID = 1231
SOURCE_PAPER_ID = 104066
ARXIV_ID = "2607.06617"
SOURCE_TITLE = "Inertia-1: An Open Exploration of Wearable Motion Foundation Models"
DATA_URL = (
    "https://archive.ics.uci.edu/dataset/507/"
    "wisdm+smartphone+and+smartwatch+activity+and+biometrics+dataset"
)
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

        parent = db.execute(
            text("SELECT id FROM datasets WHERE id = :dataset_id"),
            {"dataset_id": PARENT_DATASET_ID},
        ).scalar_one()
        if parent != PARENT_DATASET_ID:
            raise RuntimeError(f"Missing parent dataset {PARENT_DATASET_ID}")

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
                    'WISDM Smartwatch (Inertia-1 Protocol)',
                    :slug,
                    'WISDM Smartphone and Smartwatch Activity and Biometrics '
                    'Dataset — Inertia-1 Watch-Accelerometer Protocol',
                    'The reported Inertia-1 WISDM protocol uses the 2019 UCI '
                    'WISDM Smartphone and Smartwatch Activity and Biometrics '
                    'release, not the six-class WISDM v1.1 smartphone dataset. '
                    'It recognizes 18 activities from 51 participants: walking, '
                    'jogging, stairs, sitting, standing, typing, brushing teeth, '
                    'eating soup, eating chips, eating pasta, drinking from a '
                    'cup, eating a sandwich, kicking a soccer ball, playing '
                    'catch with a tennis ball, dribbling a basketball, writing, '
                    'clapping, and folding clothes. Although the release and '
                    'the preprocessing scope contain phone/watch accelerometer '
                    'and gyroscope data, the reported AUROC/AUPRC benchmark '
                    'consumes only the dominant-hand smartwatch triaxial '
                    'accelerometer.',
                    'Eighteen-class dominant-hand smartwatch activity '
                    'recognition under the frozen Inertia-1 protocol.',
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
                    '["Time Series", "Wearable Sensors", "Smartwatch", '
                    '"Accelerometer", "Dominant Wrist", '
                    '"Human Activity Recognition"]'::jsonb,
                    'Frozen subjects; 30 s/1 s; about 111.8K/24.6K/25.1K train/val/test',
                    'Protocol: use UCI dataset 507, the 2019 51-subject WISDM '
                    'Smartphone and Smartwatch Activity and Biometrics release; '
                    'do not substitute WISDM v1.1/Actitracker. Restrict raw '
                    'preprocessing to the dominant-hand LG G Watch directories, '
                    'exclude every phone file, and retain only subjects having '
                    'both watch accelerometer and gyroscope files. For each '
                    'subject, sort and deduplicate nanosecond timestamps, trim '
                    'both watch streams to their common timestamp span, split '
                    'each stream at gaps longer than one second, optionally '
                    'apply a fourth-order 10 Hz Butterworth low-pass filter when '
                    'its effective source rate exceeds 20 Hz, linearly '
                    'interpolate each axis onto a 20 Hz grid, and align activity '
                    'codes by nearest timestamp. Concatenate rebuilt segments '
                    'per stream, trim the paired streams to the common minimum '
                    'length, but select only the watch triaxial accelerometer '
                    'for this reported benchmark. Keep all 18 codes '
                    'A,B,C,D,E,F,G,H,I,J,K,L,M,O,P,Q,R,S (there is no N), mapped '
                    'respectively to walking, jogging, stairs, sitting, standing, '
                    'typing, brushing teeth, eating soup, eating chips, eating '
                    'pasta, drinking from a cup, eating a sandwich, kicking a '
                    'soccer ball, playing catch with a tennis ball, dribbling a '
                    'basketball, writing, clapping, and folding clothes. Form '
                    'overlapping 30-second windows (600 samples) with a '
                    '20-sample/one-second stride and assign each window its '
                    'majority activity. No label is unwanted in this dataset; '
                    'the generic rule nevertheless drops a window only if more '
                    'than 50% of its samples are unwanted, so no valid WISDM '
                    'activity is removed. Use the one frozen seed-0 '
                    'group-stratified train/validation/test split, grouping '
                    'windows by parsed subject ID S1600 through S1650 so no '
                    'participant crosses splits. The splitter targets '
                    '70%/15%/15% using 200 randomized greedy restarts and the '
                    'paper reports approximately 111.8K/24.6K/25.1K windows. '
                    'This is one fixed split, not cross-validation or LOSO. On '
                    'finite held-out test-window probabilities, compute '
                    'one-vs-rest ROC AUC separately for every present class and '
                    'macro-average classes equally for AUROC; compute sklearn '
                    'one-vs-rest average precision per class and macro-average '
                    'equally for AUPRC. Report both on the 0-100 percentage '
                    'scale. Linear-probe and full-finetuning results are '
                    'eligible only when their mode is identified. Exclude the '
                    'six-class WISDM v1.1 or Actitracker releases; phone input; '
                    'watch gyroscope, accelerometer-plus-gyroscope, or any '
                    'multi-stream fusion; a non-dominant-wrist interpretation; '
                    'uniaxial or magnitude input; altered preprocessing, rates, '
                    'windows, strides, labels, or splits; random-window splits, '
                    'participant overlap, LOSO, other seeds, or run/fold '
                    'averaging; and Accuracy, F1, micro/weighted AUC, or '
                    '0-1-scaled scores. The paper''s watch ACC+GYR fusion study '
                    'reports Macro F1 and requires a separate leaderboard.',
                    'https://paperswithcode.com/dataset/wisdm'
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
