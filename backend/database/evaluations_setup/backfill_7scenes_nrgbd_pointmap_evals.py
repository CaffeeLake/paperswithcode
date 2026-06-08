#!/usr/bin/env python3
"""Fix 7-Scenes / NRGBD pointmap metrics and backfill reconstruction evals.

- Replaces mis-linked classification ``Accuracy`` with ``Pointmap Accuracy`` (lower is better).
- Adds ``Normal Consistency`` to both leaderboards.
- Imports mean Acc / Comp / NC from CUT3R Table 4 and 5-view numbers from G3T Table 2
  (VGGT P/D comparators use the same protocol as reported in G3T).

Run:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/backfill_7scenes_nrgbd_pointmap_evals.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 263
DATASETS = {
    "7-scenes": 126,
    "nrgbd": 671,
}

PAPERS = {
    "g3t": (85636, "2605.27372"),
    "vggt": (46166, "2503.11651"),
    "cut3r": (43075, "2501.12387"),
}

POINTMAP_METRICS = ["Pointmap Accuracy", "Completeness", "Normal Consistency"]


@dataclass(frozen=True)
class EvalRow:
    paper_key: str
    dataset_slug: str
    model_name: str
    metric: str
    score: str
    methodology: str
    num_parameters: int | None = None


EVAL_ROWS: list[EvalRow] = [
    # G3T Table 2 — best variant per metric (5 input views, pointmap structure)
    EvalRow(
        "g3t",
        "7-scenes",
        "G3T D",
        "Pointmap Accuracy",
        "0.026",
        "Table 2 (5 views); depth-unprojected pointmaps. Lower is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    EvalRow(
        "g3t",
        "7-scenes",
        "G3T D",
        "Completeness",
        "0.029",
        "Table 2 (5 views); depth-unprojected pointmaps. Lower is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    EvalRow(
        "g3t",
        "7-scenes",
        "G3T P",
        "Normal Consistency",
        "0.793",
        "Table 2 (5 views); point-head pointmaps. Higher is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    EvalRow(
        "g3t",
        "nrgbd",
        "G3T P",
        "Pointmap Accuracy",
        "0.026",
        "Table 2 (5 views); point-head pointmaps. Lower is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    EvalRow(
        "g3t",
        "nrgbd",
        "G3T P",
        "Completeness",
        "0.021",
        "Table 2 (5 views); point-head pointmaps. Lower is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    EvalRow(
        "g3t",
        "nrgbd",
        "G3T P",
        "Normal Consistency",
        "0.907",
        "Table 2 (5 views); point-head pointmaps. Higher is better. arXiv 2605.27372.",
        1_406_749_212,
    ),
    # VGGT — same eval setup as G3T Table 2 (VGGT does not report these in its own paper)
    EvalRow(
        "vggt",
        "7-scenes",
        "VGGT P",
        "Pointmap Accuracy",
        "0.029",
        "G3T paper Table 2 (5 views); VGGT point-head. Lower is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    EvalRow(
        "vggt",
        "7-scenes",
        "VGGT D",
        "Completeness",
        "0.032",
        "G3T paper Table 2 (5 views); VGGT depth unprojection. Lower is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    EvalRow(
        "vggt",
        "7-scenes",
        "VGGT P",
        "Normal Consistency",
        "0.796",
        "G3T paper Table 2 (5 views); VGGT point-head. Higher is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    EvalRow(
        "vggt",
        "nrgbd",
        "VGGT D",
        "Pointmap Accuracy",
        "0.022",
        "G3T paper Table 2 (5 views); VGGT depth unprojection. Lower is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    EvalRow(
        "vggt",
        "nrgbd",
        "VGGT D",
        "Completeness",
        "0.018",
        "G3T paper Table 2 (5 views); VGGT depth unprojection. Lower is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    EvalRow(
        "vggt",
        "nrgbd",
        "VGGT P",
        "Normal Consistency",
        "0.921",
        "G3T paper Table 2 (5 views); VGGT point-head. Higher is better. arXiv 2605.27372.",
        1_000_000_000,
    ),
    # CUT3R Table 4 — online method, mean Acc/Comp/NC (3–5 frames on 7-Scenes, 2–4 on NRGBD)
    EvalRow(
        "cut3r",
        "7-scenes",
        "CUT3R",
        "Pointmap Accuracy",
        "0.126",
        "Table 4 mean Acc (3–5 sparse views per scene, online). Lower is better. arXiv 2501.12387.",
    ),
    EvalRow(
        "cut3r",
        "7-scenes",
        "CUT3R",
        "Completeness",
        "0.154",
        "Table 4 mean Comp (3–5 sparse views per scene, online). Lower is better. arXiv 2501.12387.",
    ),
    EvalRow(
        "cut3r",
        "7-scenes",
        "CUT3R",
        "Normal Consistency",
        "0.727",
        "Table 4 mean NC (3–5 sparse views per scene, online). Higher is better. arXiv 2501.12387.",
    ),
    EvalRow(
        "cut3r",
        "nrgbd",
        "CUT3R",
        "Pointmap Accuracy",
        "0.099",
        "Table 4 mean Acc (2–4 sparse views per scene, online). Lower is better. arXiv 2501.12387.",
    ),
    EvalRow(
        "cut3r",
        "nrgbd",
        "CUT3R",
        "Completeness",
        "0.076",
        "Table 4 mean Comp (2–4 sparse views per scene, online). Lower is better. arXiv 2501.12387.",
    ),
    EvalRow(
        "cut3r",
        "nrgbd",
        "CUT3R",
        "Normal Consistency",
        "0.837",
        "Table 4 mean NC (2–4 sparse views per scene, online). Higher is better. arXiv 2501.12387.",
    ),
]


def ensure_metric(session, name: str, direction: str, description: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"),
        {"n": name},
    ).first()
    if row:
        metric_id = int(row[0])
        session.execute(
            text(
                "UPDATE metrics SET direction = :d, description = :desc WHERE id = :id"
            ),
            {"d": direction, "desc": description, "id": metric_id},
        )
        return metric_id
    return int(
        session.execute(
            text(
                "INSERT INTO metrics (name, direction, full_name, scale, description) "
                "VALUES (:n, :d, :f, 'unbounded', :desc) RETURNING id"
            ),
            {
                "n": name,
                "d": direction,
                "f": name,
                "desc": description,
            },
        ).scalar_one()
    )


def fix_leaderboard_metrics(session) -> None:
    accuracy_id = session.execute(
        text("SELECT id FROM metrics WHERE name = 'Accuracy'")
    ).scalar_one()
    pointmap_acc_id = ensure_metric(
        session,
        "Pointmap Accuracy",
        "lower_is_better",
        "Mean point-to-surface accuracy after alignment (lower is better).",
    )
    nc_id = ensure_metric(
        session,
        "Normal Consistency",
        "higher_is_better",
        "Normal consistency of predicted pointmaps vs. ground truth (higher is better).",
    )
    completeness_id = session.execute(
        text("SELECT id FROM metrics WHERE name = 'Completeness'")
    ).scalar_one()

    for dataset_id in DATASETS.values():
        session.execute(
            text(
                "DELETE FROM task_dataset_metrics "
                "WHERE task_id = :t AND dataset_id = :d AND metric_id = :m"
            ),
            {"t": TASK_ID, "d": dataset_id, "m": accuracy_id},
        )
        for metric_id in (pointmap_acc_id, completeness_id, nc_id):
            session.execute(
                text(
                    "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
                    "VALUES (:t, :d, :m) ON CONFLICT DO NOTHING"
                ),
                {"t": TASK_ID, "d": dataset_id, "m": metric_id},
            )
    logger.info(
        "Leaderboards now use Pointmap Accuracy, Completeness, Normal Consistency "
        "(removed global Accuracy link)"
    )


def upsert_eval(session, row: EvalRow) -> str:
    paper_id, arxiv_id = PAPERS[row.paper_key]
    dataset_id = DATASETS[row.dataset_slug]
    source_url = f"https://arxiv.org/abs/{arxiv_id}"

    params = {
        "paper_id": paper_id,
        "task_id": TASK_ID,
        "dataset_id": dataset_id,
        "model_name": row.model_name,
        "harness": None,
        "best_metric": row.metric,
    }
    existing = session.execute(
        text(
            """
            SELECT id, metrics FROM evaluations
            WHERE paper_id = :paper_id AND task_id = :task_id AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = COALESCE(:harness, '')
              AND best_metric = :best_metric
            """
        ),
        params,
    ).first()

    svc = EvaluationService(session)
    if existing:
        eval_id = int(existing[0])
        session.execute(
            text(
                """
                UPDATE evaluations
                SET metrics = CAST(:metrics AS jsonb),
                    methodology = :methodology,
                    num_parameters = :num_parameters,
                    external_source_url = :source_url
                WHERE id = :id
                """
            ),
            {
                "metrics": json.dumps({row.metric: row.score}),
                "methodology": row.methodology,
                "num_parameters": row.num_parameters,
                "source_url": source_url,
                "id": eval_id,
            },
        )
        return f"updated {eval_id}"

    ev = svc.create_evaluation(
        paper_id=paper_id,
        task_id=TASK_ID,
        dataset_id=dataset_id,
        model_name=row.model_name,
        methodology=row.methodology,
        metrics={row.metric: row.score},
        best_metric=row.metric,
        harness=None,
        external_source_url=source_url,
        num_parameters=row.num_parameters,
    )
    return f"created {ev.id}"


def promote_paper_tasks(session) -> None:
    for paper_id, _ in PAPERS.values():
        session.execute(
            text(
                "INSERT INTO paper_tasks (paper_id, task_id, source) "
                "VALUES (:p, :t, 'manual') ON CONFLICT (paper_id, task_id) DO NOTHING"
            ),
            {"p": paper_id, "t": TASK_ID},
        )


def recalculate_ranks(session) -> None:
    svc = EvaluationService(session)
    for dataset_id in DATASETS.values():
        for metric in POINTMAP_METRICS:
            svc.recalculate_ranks(TASK_ID, dataset_id, metric)


def main() -> None:
    session = db_manager.session_local()
    try:
        fix_leaderboard_metrics(session)
        promote_paper_tasks(session)
        for row in EVAL_ROWS:
            result = upsert_eval(session, row)
            logger.info(
                "%s / %s / %s / %s -> %s",
                row.paper_key,
                row.dataset_slug,
                row.model_name,
                row.metric,
                result,
            )
        recalculate_ranks(session)
        session.commit()
        logger.info("Backfill complete.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
