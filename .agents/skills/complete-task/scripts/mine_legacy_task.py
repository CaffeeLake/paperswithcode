#!/usr/bin/env python3
"""Memory-safe miner for legacy Papers With Code evaluation tables.

The legacy dump ``data/legacy_pwc_data/evaluation-tables.json`` is ~250 MB, so it
must never be loaded into memory whole on the VPS. This script streams it with
``ijson`` and extracts, for a given task, the most popular benchmarks (by number
of leaderboard rows) and the top papers on each of those benchmarks.

Two modes:

1. Discover legacy task names that match a pattern (use this first — legacy task
   names rarely equal the site task slug, e.g. site ``motion-generation`` lives
   under legacy task ``Motion Synthesis``):

       uv run --env-file backend/keys.env python \
           .agents/skills/complete-task/scripts/mine_legacy_task.py \
           --list-tasks "motion|dance|gesture"

2. Aggregate benchmarks + papers for one or more exact legacy task names:

       uv run --env-file backend/keys.env python \
           .agents/skills/complete-task/scripts/mine_legacy_task.py \
           --task "Motion Synthesis" --max-benchmarks 5 --max-papers 10

Output is JSON on stdout (also written to --out if given) so a subagent or the
orchestrator can consume it directly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator

import ijson

DEFAULT_PATH = Path("data/legacy_pwc_data/evaluation-tables.json")


def iter_tasks(node: dict) -> Iterator[dict]:
    """Yield a task node and all of its nested subtasks recursively.

    Legacy items can nest arbitrarily deep under ``subtasks``; benchmarks can
    hang off any level, so we walk the whole tree.
    """
    if not isinstance(node, dict):
        return
    yield node
    for sub in node.get("subtasks", []) or []:
        yield from iter_tasks(sub)


def list_tasks(path: Path, pattern: str) -> list[str]:
    rx = re.compile(pattern, re.I)
    names: set[str] = set()
    with open(path, "rb") as fh:
        for item in ijson.items(fh, "item"):
            for task in iter_tasks(item):
                name = task.get("task")
                if name and rx.search(name):
                    names.add(name)
    return sorted(names)


def _row_paper_key(row: dict) -> str:
    """Stable identity for a leaderboard row's paper."""
    return (
        row.get("paper_url") or row.get("paper_title") or row.get("model_name") or ""
    ).strip()


def _row_signature(dname: str, row: dict) -> tuple:
    """Identity of an exact leaderboard row, used to drop duplicates.

    The same legacy task can appear more than once in the tree (e.g. both as a
    top-level item and as a subtask of a parent), which would otherwise count
    every row twice. A row is the same if it has the same benchmark, model,
    paper link, and metric values.
    """
    metrics = row.get("metrics", {}) or {}
    return (
        dname,
        row.get("model_name"),
        row.get("paper_url"),
        tuple(sorted(metrics.items())),
    )


def aggregate_task(
    path: Path,
    task_names: set[str],
    max_benchmarks: int,
    max_papers: int,
) -> dict:
    # dataset_name -> {"rows": {sig: row}, "metrics": set()}
    datasets: dict[str, dict] = {}

    with open(path, "rb") as fh:
        for item in ijson.items(fh, "item"):
            for task in iter_tasks(item):
                if task.get("task") not in task_names:
                    continue
                for ds in task.get("datasets", []) or []:
                    dname = ds.get("dataset") or ds.get("dataset_name") or "(unnamed)"
                    bucket = datasets.setdefault(dname, {"rows": {}, "metrics": set()})
                    sota = ds.get("sota", {}) or {}
                    for col in sota.get("metrics", []) or []:
                        bucket["metrics"].add(col)
                    for row in sota.get("rows", []) or []:
                        metrics = row.get("metrics", {}) or {}
                        bucket["metrics"].update(metrics.keys())
                        sig = _row_signature(dname, row)
                        # First occurrence wins; identical re-traversals are dropped.
                        bucket["rows"].setdefault(
                            sig,
                            {
                                "model_name": row.get("model_name"),
                                "metrics": metrics,
                                "paper_url": row.get("paper_url"),
                                "paper_title": row.get("paper_title"),
                                "paper_date": row.get("paper_date"),
                            },
                        )

    # Rank benchmarks by number of (deduped) leaderboard rows (popularity proxy).
    ranked = sorted(datasets.items(), key=lambda kv: len(kv[1]["rows"]), reverse=True)

    benchmarks = []
    for dname, info in ranked[:max_benchmarks]:
        rows = list(info["rows"].values())
        # Count all distinct papers across the whole benchmark (not just the cap).
        all_paper_keys = {_row_paper_key(r) for r in rows if _row_paper_key(r)}
        # Top papers: dedupe by paper key, keep first occurrence, cap at max_papers.
        seen: set[str] = set()
        papers = []
        for row in rows:
            key = _row_paper_key(row)
            if not key or key in seen:
                continue
            seen.add(key)
            papers.append(row)
            if len(papers) >= max_papers:
                break
        benchmarks.append(
            {
                "benchmark": dname,
                "row_count": len(rows),
                "unique_papers": len(all_paper_keys),
                "metrics": sorted(info["metrics"]),
                "top_papers": papers,
            }
        )

    return {
        "legacy_tasks": sorted(task_names),
        "benchmark_count": len(datasets),
        "benchmarks": benchmarks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help="Path to legacy evaluation-tables.json (default: %(default)s)",
    )
    ap.add_argument(
        "--list-tasks",
        metavar="REGEX",
        help="Discovery mode: print legacy task names matching this regex.",
    )
    ap.add_argument(
        "--task",
        action="append",
        default=[],
        metavar="NAME",
        help="Exact legacy task name to aggregate (repeatable).",
    )
    ap.add_argument("--max-benchmarks", type=int, default=5)
    ap.add_argument("--max-papers", type=int, default=10)
    ap.add_argument(
        "--out",
        type=Path,
        help="Optional path to also write the JSON result to.",
    )
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"ERROR: legacy file not found: {args.path}", file=sys.stderr)
        return 2

    if args.list_tasks:
        names = list_tasks(args.path, args.list_tasks)
        result = {"pattern": args.list_tasks, "matches": names}
    elif args.task:
        result = aggregate_task(
            args.path,
            set(args.task),
            max_benchmarks=args.max_benchmarks,
            max_papers=args.max_papers,
        )
    else:
        ap.error("Provide either --list-tasks REGEX or one/more --task NAME")
        return 2

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
