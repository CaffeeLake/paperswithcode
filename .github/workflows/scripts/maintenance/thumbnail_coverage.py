"""
Thumbnail Coverage Report (read-only)

Reports how many paper thumbnails are present on the VPS local cache for the
priority sets used by the homepage, task pages, and the full database. Useful
for verifying that the preload_thumbnails cron modes are keeping up.

The script never writes anything. It only inspects PWC_THUMBNAIL_TEMP_CACHE_DIR
(or PWC_THUMBNAIL_CACHE_DIR when storage is local) and the PostgreSQL papers
table.

Usage:
    PYTHONPATH=.github/workflows \
        uv run --env-file backend/keys.env \
        python -m scripts.maintenance.thumbnail_coverage

    PYTHONPATH=.github/workflows \
        uv run --env-file backend/keys.env \
        python -m scripts.maintenance.thumbnail_coverage --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.thumbnail_service import build_thumbnail_filename


DEFAULT_TRENDING_LIMIT = 500
DEFAULT_TRENDING_MAX_AGE_DAYS = 180
DEFAULT_PER_TASK = 50


def _cache_dir() -> Path:
    settings = get_settings()
    if (settings.thumbnail_storage_backend or "").lower() == "hf_bucket":
        return Path(settings.thumbnail_temp_cache_dir)
    return Path(settings.thumbnail_cache_dir)


def _existing_filenames(cache_dir: Path) -> set:
    if not cache_dir.exists():
        return set()
    return {p.name for p in cache_dir.glob("*.jpg")}


def _coverage(rows, existing: set) -> Dict[str, int]:
    expected = {
        build_thumbnail_filename(arxiv_id, version or "v1")
        for _, arxiv_id, version in rows
        if arxiv_id
    }
    present = expected & existing
    missing = expected - existing
    return {
        "unique_papers": len(expected),
        "present": len(present),
        "missing": len(missing),
        "coverage_pct": round(
            (len(present) / len(expected) * 100.0) if expected else 0.0, 2
        ),
    }


def _query_trending(session, limit: int, max_age_days: int) -> List[Tuple]:
    sql = text(
        """
        WITH ranked AS (
            SELECT DISTINCT ON (tp.paper_id)
                tp.paper_id,
                tp.arxiv_id,
                p.version,
                tp.trending_score,
                tp.current_stars
            FROM trending_papers_24h tp
            JOIN papers p ON p.id = tp.paper_id
            WHERE tp.paper_age_days <= :max_age_days
              AND tp.arxiv_id IS NOT NULL
              AND tp.arxiv_id <> ''
            ORDER BY tp.paper_id,
                     tp.trending_score DESC NULLS LAST,
                     tp.current_stars DESC
        )
        SELECT paper_id, arxiv_id, version
        FROM ranked
        ORDER BY trending_score DESC NULLS LAST, current_stars DESC
        LIMIT :limit
        """
    )
    return [
        (row[0], row[1], row[2])
        for row in session.execute(sql, {"limit": limit, "max_age_days": max_age_days})
    ]


def _query_task_top(session, per_task: int) -> List[Tuple]:
    sql = text(
        """
        WITH scored AS (
            SELECT
                pt.task_id,
                p.id AS paper_id,
                p.arxiv_id,
                p.version,
                p.date_published,
                COALESCE(MAX(r.trending_score), 0)        AS trending_score,
                COALESCE(MAX(r.num_stars), 0)              AS stars
            FROM paper_tasks pt
            JOIN papers p ON p.id = pt.paper_id
            LEFT JOIN paper_repositories pr
              ON pr.paper_id = p.id AND pr.is_official = TRUE
            LEFT JOIN repositories r ON r.id = pr.repository_id
            WHERE p.is_latest_version
              AND p.arxiv_id IS NOT NULL
              AND p.arxiv_id <> ''
            GROUP BY pt.task_id, p.id, p.arxiv_id, p.version, p.date_published
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY task_id
                ORDER BY trending_score DESC NULLS LAST,
                         stars DESC NULLS LAST,
                         date_published DESC NULLS LAST,
                         paper_id DESC
            ) AS rn
            FROM scored
        )
        SELECT DISTINCT ON (paper_id) paper_id, arxiv_id, version
        FROM ranked
        WHERE rn <= :per_task
        ORDER BY paper_id
        """
    )
    return [
        (row[0], row[1], row[2]) for row in session.execute(sql, {"per_task": per_task})
    ]


def _query_all_latest_arxiv(session) -> List[Tuple]:
    sql = text(
        """
        SELECT id, arxiv_id, version
        FROM papers
        WHERE is_latest_version
          AND arxiv_id IS NOT NULL
          AND arxiv_id <> ''
        """
    )
    return [(row[0], row[1], row[2]) for row in session.execute(sql)]


def collect_report(
    trending_limit: int,
    trending_max_age_days: int,
    per_task: int,
) -> Dict[str, Dict[str, int]]:
    cache_dir = _cache_dir()
    existing = _existing_filenames(cache_dir)
    report: Dict[str, Dict[str, int]] = {}

    with db_manager.session_local() as session:
        report[f"top_trending_{trending_limit}"] = _coverage(
            _query_trending(session, trending_limit, trending_max_age_days),
            existing,
        )
        report[f"top_{per_task}_per_task"] = _coverage(
            _query_task_top(session, per_task), existing
        )
        report["all_latest_arxiv"] = _coverage(
            _query_all_latest_arxiv(session), existing
        )

    report["_meta"] = {
        "cache_dir": str(cache_dir),
        "local_jpg_files": len(existing),
    }
    return report


def _print_table(report: Dict[str, Dict[str, int]]) -> None:
    meta = report.get("_meta", {})
    print(f"Cache dir: {meta.get('cache_dir')}")
    print(f"Local JPGs on disk: {meta.get('local_jpg_files')}")
    print()
    print(
        f"{'segment':<28} {'papers':>10} {'present':>10} {'missing':>10} {'coverage':>10}"
    )
    print("-" * 72)
    for name, stats in report.items():
        if name.startswith("_"):
            continue
        print(
            f"{name:<28} {stats['unique_papers']:>10d} "
            f"{stats['present']:>10d} {stats['missing']:>10d} "
            f"{stats['coverage_pct']:>9.2f}%"
        )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report thumbnail coverage for top trending, top-N-per-task, and "
            "all latest-version arXiv papers."
        )
    )
    parser.add_argument(
        "--trending-limit",
        type=int,
        default=DEFAULT_TRENDING_LIMIT,
        help="Top N trending papers to evaluate (default: %(default)s).",
    )
    parser.add_argument(
        "--trending-max-age-days",
        type=int,
        default=DEFAULT_TRENDING_MAX_AGE_DAYS,
        help="Maximum paper age for trending eligibility (default: %(default)s).",
    )
    parser.add_argument(
        "--per-task",
        type=int,
        default=DEFAULT_PER_TASK,
        help="Top N papers per task to evaluate (default: %(default)s).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a text table.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    report = collect_report(
        trending_limit=args.trending_limit,
        trending_max_age_days=args.trending_max_age_days,
        per_task=args.per_task,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
