"""
Cross-check legacy gap CSV eval_missing rows against the live DB.

Filters stale CSV rows (eval already imported) and flags metric blockers
where legacy labels do not map to configured leaderboard metrics.

Usage:
  uv run --env-file backend/keys.env python \\
    backend/database/evaluations_setup/list_fresh_eval_missing.py

  uv run --env-file backend/keys.env python \\
    backend/database/evaluations_setup/list_fresh_eval_missing.py \\
    --rank 1 --csv data/legacy_top_ranked_missing_evals.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager

DEFAULT_CSV = Path("data/legacy_top_ranked_missing_evals.csv")

# Legacy label (lower) -> configured metric name candidates (first match wins).
LEGACY_METRIC_ALIASES: dict[str, list[str]] = {
    "map": ["mAP", "MAP"],
    "box ap": ["mAP", "box AP"],
    "box map": ["mAP", "box AP"],
    "average map": ["mAP"],
    "top 1 accuracy": ["Top-1 Accuracy", "Accuracy"],
    "top-1 accuracy": ["Top-1 Accuracy", "Accuracy"],
    "accuracy (%)": ["Accuracy", "Top-1 Accuracy"],
    "percentage correct": ["Accuracy", "Top-1 Accuracy"],
    "top 5 accuracy": ["Top-5 Accuracy"],
    "val miou": ["mIoU"],
    "test miou": ["mIoU"],
    "miou": ["mIoU"],
    "exact match accuracy (in dev)": ["Exact Match"],
    "exact match": ["Exact Match"],
    "f1": ["F1"],
    "micro f1": ["F1"],
    "fid": ["FID"],
    "meteor": ["METEOR"],
    "rouge-l": ["ROUGE-L"],
    "delta < 1.25": ["delta1", "AbsRel"],
}


def parse_legacy_metrics(raw: str) -> list[str]:
    if not raw:
        return []
    keys = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        key = part.split("=", 1)[0].strip()
        if key:
            keys.append(key)
    return keys


def map_legacy_metric(label: str, allowed: set[str]) -> str | None:
    if label in allowed:
        return label
    candidates = LEGACY_METRIC_ALIASES.get(label.lower(), [])
    for name in candidates:
        if name in allowed:
            return name
    return None


def load_db_state(db):
    tasks_by_slug = {
        row.slug: row.id for row in db.execute(text("SELECT id, slug FROM tasks")).all()
    }
    datasets_by_slug = {
        row.slug: row.id
        for row in db.execute(text("SELECT id, slug FROM datasets")).all()
    }
    paper_id_by_arxiv = {
        row.arxiv_id: row.id
        for row in db.execute(
            text(
                "SELECT id, arxiv_id FROM papers "
                "WHERE is_latest_version AND arxiv_id IS NOT NULL"
            )
        ).all()
    }
    eval_keys = set(
        db.execute(text("SELECT paper_id, task_id, dataset_id FROM evaluations")).all()
    )
    allowed_metrics: dict[tuple[int, int], set[str]] = {}
    for row in db.execute(
        text(
            """
            SELECT tdm.task_id, tdm.dataset_id, m.name
            FROM task_dataset_metrics tdm
            JOIN metrics m ON m.id = tdm.metric_id
            """
        )
    ).all():
        allowed_metrics.setdefault((row.task_id, row.dataset_id), set()).add(row.name)
    return (
        tasks_by_slug,
        datasets_by_slug,
        paper_id_by_arxiv,
        eval_keys,
        allowed_metrics,
    )


def classify_row(row: dict, db_state) -> tuple[str, str]:
    (
        tasks_by_slug,
        datasets_by_slug,
        paper_id_by_arxiv,
        eval_keys,
        allowed_metrics,
    ) = db_state

    task_slug = row.get("db_task_slug") or ""
    dataset_slug = row.get("db_dataset_slug") or ""
    arxiv_id = row.get("arxiv_id") or ""

    task_id = tasks_by_slug.get(task_slug)
    dataset_id = datasets_by_slug.get(dataset_slug)
    if not task_id or not dataset_id:
        return "infra_missing", "task or dataset slug not in DB"

    paper_id = paper_id_by_arxiv.get(arxiv_id)
    if not paper_id:
        return "paper_missing", "paper not indexed"

    if (paper_id, task_id, dataset_id) in eval_keys:
        return "stale", "eval row already exists"

    allowed = allowed_metrics.get((task_id, dataset_id), set())
    if not allowed:
        return "no_metrics", "leaderboard has no configured metrics"

    legacy_keys = parse_legacy_metrics(row.get("metrics", ""))
    if not legacy_keys:
        return "ready", "no legacy metric keys to map"

    mapped = [map_legacy_metric(k, allowed) for k in legacy_keys]
    usable = [m for m in mapped if m is not None]
    if not usable:
        unmapped = [k for k, m in zip(legacy_keys, mapped) if m is None]
        return (
            "metric_blocked",
            f"unmapped legacy labels: {', '.join(unmapped)} "
            f"(allowed: {', '.join(sorted(allowed))})",
        )

    detail = f"maps to {', '.join(dict.fromkeys(usable))}"
    skipped = [k for k, m in zip(legacy_keys, mapped) if m is None]
    if skipped:
        detail += f"; skip unmapped: {', '.join(skipped)}"
    return "ready", detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--rank", type=int, default=None, help="Filter by legacy_rank")
    parser.add_argument(
        "--status",
        default="ready",
        help="Output filter: ready, all, stale, metric_blocked, …",
    )
    args = parser.parse_args()

    rows = []
    with args.csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "eval_missing":
                continue
            if args.rank is not None and int(row["legacy_rank"]) != args.rank:
                continue
            rows.append(row)

    with db_manager.session_local() as db:
        db_state = load_db_state(db)
        classified: list[tuple[str, str, dict]] = []
        for row in rows:
            outcome, detail = classify_row(row, db_state)
            classified.append((outcome, detail, row))

    counts = Counter(c[0] for c in classified)
    print(f"CSV eval_missing rows checked: {len(rows)}")
    print("Live DB cross-check:")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")

    show = args.status
    if show != "all":
        classified = [c for c in classified if c[0] == show]

    print(f"\nRows ({show}):")
    for outcome, detail, row in sorted(
        classified, key=lambda x: (int(x[2]["legacy_rank"]), x[2]["arxiv_id"])
    ):
        print(
            f"  #{row['legacy_rank']} {row['arxiv_id']} {row['model_name'][:45]:45} | "
            f"{row['db_task']} / {row['db_dataset']} | {row['metrics']} | "
            f"[{outcome}] {detail}"
        )


if __name__ == "__main__":
    main()
