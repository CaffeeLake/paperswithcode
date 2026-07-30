#!/usr/bin/env python3
"""Read-only inventory for one or more Hugging Face daily-paper cohorts."""

from __future__ import annotations

import argparse
import json
import subprocess

from sqlalchemy import bindparam, text

from backend.database.connection import db_manager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        action="append",
        required=True,
        help="UTC daily-paper date (YYYY-MM-DD); repeat for multiple dates",
    )
    return parser.parse_args()


def fetch_daily_ids(day: str) -> list[str]:
    result = subprocess.run(
        [
            "hf",
            "papers",
            "list",
            "--date",
            day,
            "--limit",
            "100",
            "--format",
            "quiet",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    ids_by_date = {day: fetch_daily_ids(day) for day in args.date}
    ordered_ids = list(
        dict.fromkeys(arxiv_id for ids in ids_by_date.values() for arxiv_id in ids)
    )

    if not ordered_ids:
        print(json.dumps({"dates": ids_by_date, "papers": [], "missing": []}, indent=2))
        return

    query = text(
        """
        SELECT
            p.id,
            p.arxiv_id,
            p.title,
            COALESCE(array_agg(DISTINCT t.slug)
                FILTER (WHERE t.slug IS NOT NULL), '{}') AS tasks,
            COALESCE(array_agg(DISTINCT m.slug)
                FILTER (WHERE m.slug IS NOT NULL), '{}') AS methods,
            COUNT(DISTINCT e.id) AS evaluation_count
        FROM papers p
        LEFT JOIN paper_tasks pt ON pt.paper_id = p.id
        LEFT JOIN tasks t ON t.id = pt.task_id
        LEFT JOIN paper_methods pm ON pm.paper_id = p.id
        LEFT JOIN methods m ON m.id = pm.method_id
        LEFT JOIN evaluations e ON e.paper_id = p.id
        WHERE p.arxiv_id IN :ids
        GROUP BY p.id, p.arxiv_id, p.title
        """
    ).bindparams(bindparam("ids", expanding=True))

    with db_manager.engine.connect() as conn:
        rows = conn.execute(query, {"ids": ordered_ids}).mappings().all()

    by_id = {row.arxiv_id: dict(row) for row in rows}
    papers = [by_id[arxiv_id] for arxiv_id in ordered_ids if arxiv_id in by_id]
    missing = [arxiv_id for arxiv_id in ordered_ids if arxiv_id not in by_id]
    print(
        json.dumps(
            {
                "dates": ids_by_date,
                "cohort_size": len(ordered_ids),
                "papers": papers,
                "missing": missing,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
