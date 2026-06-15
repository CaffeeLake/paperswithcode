"""
Stream legacy PwC evaluation-tables.json and find top-ranked SOTA rows
missing from our database (benchmark not linked and/or eval row absent).

Uses ijson streaming — safe on low-RAM VPS. Does not load papers-with-abstracts.json.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import ijson
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.utils.dataset_utils import find_dataset_by_name

ARXIV_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
DEFAULT_PATH = Path("data/legacy_pwc_data/evaluation-tables.json")


@dataclass(frozen=True)
class LegacyRow:
    sota_slug: str
    task_name: str
    dataset_name: str
    rank: int
    arxiv_id: str
    paper_title: str
    model_name: str
    metrics: str


def extract_arxiv_id(paper_url: str | None) -> str | None:
    if not paper_url:
        return None
    m = ARXIV_RE.search(paper_url)
    return m.group(1) if m else None


def sota_slug(ds: dict) -> str | None:
    for link in ds.get("dataset_links", []):
        url = link.get("url", "")
        if "paperswithcode.com/sota/" in url:
            return url.split("/sota/")[-1].rstrip("/")
    return None


def walk_leaderboards(
    node: dict, leaf_task: str
) -> Iterator[tuple[str | None, str, dict]]:
    task = node.get("task") or leaf_task
    for ds in node.get("datasets", []):
        rows = ds.get("sota", {}).get("rows", [])
        if rows:
            yield sota_slug(ds), task, ds
    for sub in node.get("subtasks", []):
        yield from walk_leaderboards(sub, task)


def format_metrics(metrics: dict | None) -> str:
    if not metrics:
        return ""
    parts = [f"{k}={v}" for k, v in metrics.items()]
    return "; ".join(parts)


def load_db_indexes(db):
    tasks_by_name = {}
    for row in db.execute(text("SELECT id, slug, name FROM tasks")).all():
        tasks_by_name[row.name.lower()] = row
        tasks_by_name[row.slug.replace("-", " ")] = row

    datasets_by_id = {
        row.id: row
        for row in db.execute(text("SELECT id, slug, name FROM datasets")).all()
    }

    task_datasets = set(
        db.execute(text("SELECT task_id, dataset_id FROM task_datasets")).all()
    )

    paper_id_by_arxiv = {
        row.arxiv_id: row.id
        for row in db.execute(
            text(
                "SELECT id, arxiv_id FROM papers WHERE is_latest_version AND arxiv_id IS NOT NULL"
            )
        ).all()
    }

    eval_keys = set(
        db.execute(text("SELECT paper_id, task_id, dataset_id FROM evaluations")).all()
    )

    return (
        tasks_by_name,
        datasets_by_id,
        task_datasets,
        paper_id_by_arxiv,
        eval_keys,
    )


def match_task(tasks_by_name: dict, task_name: str, sota: str | None):
    if not task_name:
        return None
    direct = tasks_by_name.get(task_name.lower())
    if direct:
        return direct
    if sota:
        prefix = sota.split("-on-")[0].replace("-", " ")
        hit = tasks_by_name.get(prefix)
        if hit:
            return hit
    words = task_name.lower().split()
    for n in (3, 2, 1):
        key = " ".join(words[-n:])
        if key in tasks_by_name:
            return tasks_by_name[key]
    return None


def match_dataset(db, dataset_name: str, sota: str | None):
    ds = find_dataset_by_name(db, dataset_name)
    if ds:
        return ds
    if not sota or "-on-" not in sota:
        return None
    tail = sota.split("-on-", 1)[1]
    slug_candidates = [tail]
    if not tail.endswith("-test") and not tail.endswith("-val"):
        slug_candidates.extend([f"{tail}-test", f"{tail}-val"])
    for slug in slug_candidates:
        row = db.execute(
            text("SELECT id, slug, name FROM datasets WHERE slug = :slug"),
            {"slug": slug},
        ).first()
        if row:
            return row
    return None


def stream_legacy_top_rows(path: Path, max_rank: int) -> dict[str, list[LegacyRow]]:
    """Return unique leaderboards (by sota slug) -> top rows up to max_rank."""
    by_slug: dict[str, list[LegacyRow]] = {}
    with path.open("rb") as f:
        for item in ijson.items(f, "item"):
            root_task = item.get("task", "")
            for slug, task_name, ds in walk_leaderboards(item, root_task):
                rows = ds.get("sota", {}).get("rows", [])
                if not rows:
                    continue
                key = slug or f"{task_name}|{ds.get('dataset', '')}"
                if key in by_slug:
                    continue
                parsed: list[LegacyRow] = []
                for idx, row in enumerate(rows[:max_rank], start=1):
                    arxiv_id = extract_arxiv_id(row.get("paper_url"))
                    if not arxiv_id:
                        continue
                    parsed.append(
                        LegacyRow(
                            sota_slug=key,
                            task_name=task_name,
                            dataset_name=ds.get("dataset", ""),
                            rank=idx,
                            arxiv_id=arxiv_id,
                            paper_title=row.get("paper_title", ""),
                            model_name=row.get("model_name", ""),
                            metrics=format_metrics(row.get("metrics")),
                        )
                    )
                if parsed:
                    by_slug[key] = parsed
    return by_slug


def classify_row(
    row, db_ctx, dataset_cache: dict[str, object | None]
) -> tuple[str, object | None, object | None]:
    tasks_by_name, _, task_datasets, paper_id_by_arxiv, eval_keys, db = db_ctx

    task = match_task(tasks_by_name, row.task_name, row.sota_slug)
    cache_key = f"{row.dataset_name}|{row.sota_slug}"
    if cache_key not in dataset_cache:
        dataset_cache[cache_key] = match_dataset(db, row.dataset_name, row.sota_slug)
    dataset = dataset_cache[cache_key]
    paper_id = paper_id_by_arxiv.get(row.arxiv_id)

    if not task or not dataset:
        return "unmapped_leaderboard", task, dataset
    if (task.id, dataset.id) not in task_datasets:
        return "benchmark_missing", task, dataset
    if not paper_id:
        return "paper_missing", task, dataset
    if (paper_id, task.id, dataset.id) not in eval_keys:
        return "eval_missing", task, dataset
    return "present", task, dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rank", type=int, default=3)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=Path("data/legacy_top_ranked_missing_evals.csv"),
    )
    args = parser.parse_args()

    print(f"Streaming legacy leaderboards from {args.path} …")
    leaderboards = stream_legacy_top_rows(args.path, args.max_rank)
    print(f"Unique legacy leaderboards: {len(leaderboards)}")

    with db_manager.session_local() as db:
        db_ctx = (*load_db_indexes(db), db)
        missing_rows: list[dict] = []
        status_counts: Counter[str] = Counter()
        benchmark_gaps: Counter[tuple[str, str, str]] = Counter()
        dataset_cache: dict[str, object | None] = {}

        for slug, rows in leaderboards.items():
            for row in rows:
                status, task, dataset = classify_row(row, db_ctx, dataset_cache)
                status_counts[status] += 1
                if status == "present":
                    continue
                rec = {
                    "status": status,
                    "legacy_rank": row.rank,
                    "sota_slug": row.sota_slug,
                    "legacy_task": row.task_name,
                    "legacy_dataset": row.dataset_name,
                    "arxiv_id": row.arxiv_id,
                    "paper_title": row.paper_title,
                    "model_name": row.model_name,
                    "metrics": row.metrics,
                    "db_task": getattr(task, "name", ""),
                    "db_task_slug": getattr(task, "slug", ""),
                    "db_dataset": getattr(dataset, "name", ""),
                    "db_dataset_slug": getattr(dataset, "slug", ""),
                }
                missing_rows.append(rec)
                if status in ("benchmark_missing", "unmapped_leaderboard"):
                    benchmark_gaps[(row.task_name, row.dataset_name, status)] += 1

    missing_rows.sort(key=lambda r: (r["legacy_rank"], r["status"], r["sota_slug"]))

    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    if missing_rows:
        with args.csv_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(missing_rows[0].keys()))
            writer.writeheader()
            writer.writerows(missing_rows)
    print(f"Wrote {len(missing_rows)} gap rows to {args.csv_out}")

    print("\nStatus counts (top rank ≤ {0} per leaderboard):".format(args.max_rank))
    for k, v in status_counts.most_common():
        print(f"  {k}: {v}")

    rank1_missing = [r for r in missing_rows if r["legacy_rank"] == 1]
    print(f"\nRank-1 gaps: {len(rank1_missing)}")

    by_benchmark = Counter(
        (r["legacy_task"], r["legacy_dataset"], r["status"]) for r in rank1_missing
    )
    print("\nTop rank-1 benchmark gaps (legacy task | dataset | status):")
    for (task, dataset, status), n in by_benchmark.most_common(25):
        print(f"  [{status}] {task} | {dataset}")

    eval_missing_rank1 = [r for r in rank1_missing if r["status"] == "eval_missing"]
    print(f"\nRank-1 eval_missing where benchmark exists ({len(eval_missing_rank1)}):")
    for r in eval_missing_rank1[:30]:
        print(
            f"  #{r['legacy_rank']} {r['arxiv_id']} {r['model_name'][:40]} | "
            f"{r['db_task']} / {r['db_dataset']}"
        )

    unmapped_rank1 = [r for r in rank1_missing if r["status"] == "unmapped_leaderboard"]
    unmapped_by_ds = Counter(r["legacy_dataset"] for r in unmapped_rank1)
    print("\nMost common unmapped rank-1 datasets (need benchmark + eval pipeline):")
    for ds, n in unmapped_by_ds.most_common(20):
        print(f"  {n}x {ds}")

    bench_missing_rank1 = [
        r for r in rank1_missing if r["status"] == "benchmark_missing"
    ]
    bench_by_ds = Counter(
        (r["db_task"] or r["legacy_task"], r["legacy_dataset"])
        for r in bench_missing_rank1
    )
    print("\nRank-1 benchmark_missing (dataset exists, not linked to task):")
    for (task, ds), n in bench_by_ds.most_common(20):
        print(f"  {n}x {task} | {ds}")


if __name__ == "__main__":
    main()
