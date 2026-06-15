#!/usr/bin/env python3
"""Import 14 legacy PwC nuScenes 3D object detection eval rows (papers already in DB)."""

from __future__ import annotations

import logging
from pathlib import Path

import ijson
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.evaluations_setup.analyze_legacy_top_ranked_gaps import (
    extract_arxiv_id,
    walk_leaderboards,
)
from backend.models.database import Evaluation as DBEvaluation
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 333
DATASET_ID = 677
LEGACY_PATH = Path("data/legacy_pwc_data/evaluation-tables.json")
SOTA_SLUG = "3d-object-detection-on-nuscenes"

TARGET_MODELS = {
    ("2205.13542", "BEVFusion-e"),
    ("2308.04556", "FocalFormer3D-F"),
    ("2308.04556", "FocalFormer3D-TTA"),
    ("2308.04556", "FocalFormer3D-L"),
    ("2301.06051", "DSVT"),
    ("2006.11275", "CenterPoint"),
    ("2411.19860", "SpaRC"),
    ("2403.07746", "HyDRa"),
    ("2304.00670", "CRN"),
    ("2203.17270", "BEVFormer"),
    ("1903.11027", "PointPillars (ImageNet)"),
    ("1903.11027", "PointPillars (KITTI)"),
    ("1903.11027", "PointPillars"),
    ("2104.10956", "FCOS3D"),
}


def load_legacy_rows() -> dict[tuple[str, str], dict]:
    rows_out = None
    with LEGACY_PATH.open("rb") as f:
        for item in ijson.items(f, "item"):
            for slug, _, ds in walk_leaderboards(item, item.get("task", "")):
                if slug == SOTA_SLUG:
                    rows_out = ds.get("sota", {}).get("rows", [])
                    break
            if rows_out:
                break
    if not rows_out:
        raise RuntimeError(f"Leaderboard {SOTA_SLUG!r} not found in legacy data")

    found: dict[tuple[str, str], dict] = {}
    for row in rows_out:
        arxiv = extract_arxiv_id(row.get("paper_url"))
        model = row.get("model_name", "")
        key = (arxiv, model)
        if key in TARGET_MODELS and key not in found:
            found[key] = row
    missing = TARGET_MODELS - found.keys()
    if missing:
        raise RuntimeError(f"Missing legacy rows for: {missing}")
    return found


def to_leaderboard_score(raw: str) -> str:
    value = float(raw)
    if value <= 1.0:
        scaled = value * 100
        return str(int(scaled)) if scaled.is_integer() else f"{scaled:g}"
    return raw


def link_paper_task(session, paper_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": TASK_ID},
    )


def main() -> None:
    legacy_rows = load_legacy_rows()
    session = db_manager.session_local()
    created = 0
    skipped = 0
    linked_papers: set[int] = set()
    try:
        service = EvaluationService(session)
        for (arxiv_id, model_name), row in sorted(
            legacy_rows.items(), key=lambda x: (x[0][0], x[0][1])
        ):
            session.rollback()
            paper = session.execute(
                text("SELECT id FROM papers WHERE arxiv_id = :a AND is_latest_version"),
                {"a": arxiv_id},
            ).first()
            if not paper:
                raise RuntimeError(f"Paper {arxiv_id} not in DB")
            paper_id = int(paper.id)
            if paper_id not in linked_papers:
                link_paper_task(session, paper_id)
                session.commit()
                linked_papers.add(paper_id)

            metrics = row.get("metrics") or {}
            methodology = (
                "nuScenes test split; scores from legacy PapersWithCode "
                f"evaluation-tables.json ({SOTA_SLUG}); source: arXiv {arxiv_id}. "
                "NDS/mAP converted from 0–1 scale to percentage to match leaderboard."
            )
            source_url = f"https://arxiv.org/abs/{arxiv_id}"

            for metric in ("NDS", "mAP"):
                if metric not in metrics:
                    continue
                score = to_leaderboard_score(str(metrics[metric]))
                session.rollback()
                exists = (
                    session.query(DBEvaluation)
                    .filter(
                        DBEvaluation.paper_id == paper_id,
                        DBEvaluation.task_id == TASK_ID,
                        DBEvaluation.dataset_id == DATASET_ID,
                        DBEvaluation.model_name == model_name,
                        DBEvaluation.best_metric == metric,
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    logger.info(
                        "Skip existing %s / %s / %s", arxiv_id, model_name, metric
                    )
                    continue

                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=TASK_ID,
                    dataset_id=DATASET_ID,
                    model_name=model_name,
                    methodology=methodology,
                    metrics={metric: score},
                    best_metric=metric,
                    external_source_url=source_url,
                    is_open=True,
                )
                created += 1
                logger.info(
                    "Created %s / %s / %s = %s", arxiv_id, model_name, metric, score
                )

        logger.info("Done: %s rows created, %s skipped", created, skipped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
