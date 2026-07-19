"""Benchmark legacy and weighted-FTS paper search against the relevance fixture.

Example:
    uv run --env-file backend/keys.env python \
      backend/scripts/benchmark_paper_search.py --database-url postgresql://... \
      --iterations 3 --output /tmp/paper-search-benchmark.json
"""

import argparse
import json
import math
import statistics
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.services.paper_service import PaperService


DEFAULT_FIXTURE = (
    Path(__file__).parents[1] / "tests" / "fixtures" / "paper_search_relevance.json"
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def metrics(cases: list[dict], result_ids: list[list[str | None]]) -> dict:
    reciprocal_ranks = []
    recalls = []
    ndcgs = []
    expected_top1 = []
    required_rank_checks = []
    for case, ranked in zip(cases, result_ids, strict=True):
        if expected := case.get("expected_top"):
            expected_top1.append(bool(ranked) and ranked[0] == expected)
        for requirement in case.get("required", []):
            rank = next(
                (
                    rank
                    for rank, paper_id in enumerate(ranked, 1)
                    if paper_id == requirement["arxiv_id"]
                ),
                None,
            )
            required_rank_checks.append(
                rank is not None and rank <= requirement["max_rank"]
            )
        judgments = {
            item["arxiv_id"]: item.get("grade", 1) for item in case["relevant"]
        }
        if not judgments:
            continue
        first_rank = next(
            (
                rank
                for rank, paper_id in enumerate(ranked[:10], 1)
                if paper_id in judgments
            ),
            None,
        )
        reciprocal_ranks.append(1 / first_rank if first_rank else 0)
        recalls.append(len(set(ranked[:20]) & judgments.keys()) / len(judgments))
        dcg = sum(
            (2 ** judgments.get(paper_id, 0) - 1) / math.log2(rank + 1)
            for rank, paper_id in enumerate(ranked[:10], 1)
        )
        ideal = sum(
            (2**grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(
                sorted(judgments.values(), reverse=True)[:10], 1
            )
        )
        ndcgs.append(dcg / ideal if ideal else 0)
    return {
        "mrr_at_10": statistics.fmean(reciprocal_ranks) if reciprocal_ranks else None,
        "ndcg_at_10": statistics.fmean(ndcgs) if ndcgs else None,
        "recall_at_20": statistics.fmean(recalls) if recalls else None,
        "expected_top1_accuracy": (
            statistics.fmean(expected_top1) if expected_top1 else None
        ),
        "expected_top1_passed": sum(expected_top1),
        "expected_top1_total": len(expected_top1),
        "required_rank_accuracy": (
            statistics.fmean(required_rank_checks) if required_rank_checks else None
        ),
        "required_rank_passed": sum(required_rank_checks),
        "required_rank_total": len(required_rank_checks),
    }


def benchmark(
    database_url: str,
    fixture_path: Path,
    iterations: int,
    limit: int,
    modes: list[str] | None = None,
) -> dict:
    cases = json.loads(fixture_path.read_text())
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    report = {"fixture": str(fixture_path), "query_count": len(cases), "modes": {}}
    try:
        with sessions() as session:
            for mode in modes or ["keyword", "semantic", "hybrid"]:
                service = PaperService(session)
                service.settings.paper_search_mode = mode
                rows = []
                all_latencies = []
                ranked_ids = []
                for case in cases:
                    samples = []
                    results = []
                    for _ in range(iterations):
                        started = time.perf_counter()
                        results = service.search_papers(case["query"], limit)
                        samples.append((time.perf_counter() - started) * 1_000)
                    all_latencies.extend(samples)
                    arxiv_ids = [result.arxiv_id for result in results]
                    ranked_ids.append(arxiv_ids)
                    rows.append(
                        {
                            "query": case["query"],
                            "latency_ms": statistics.median(samples),
                            "results": [
                                {
                                    "id": result.id,
                                    "arxiv_id": result.arxiv_id,
                                    "title": result.title,
                                    "citation_count": result.citation_count,
                                }
                                for result in results
                            ],
                        }
                    )
                report["modes"][mode] = {
                    "latency_ms": {
                        "p50": percentile(all_latencies, 0.50),
                        "p95": percentile(all_latencies, 0.95),
                    },
                    **metrics(cases, ranked_ids),
                    "queries": rows,
                }

            with engine.connect() as connection:
                report["plans"] = {}
                report["plans"]["keyword"] = [
                    row[0]
                    for row in connection.execute(
                        text("""
                            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                            WITH candidates AS (
                                SELECT
                                    id AS paper_id,
                                    1 AS identity_tier,
                                    ts_rank_cd(
                                        search_vector,
                                        websearch_to_tsquery('english', :query),
                                        32
                                    ) AS lexical_rank
                                FROM papers
                                WHERE is_latest_version
                                  AND lower(regexp_replace(
                                      btrim(title), '\\s+', ' ', 'g'
                                  )) = :normalized_title
                                UNION ALL
                                SELECT
                                    id AS paper_id,
                                    2 AS identity_tier,
                                    ts_rank_cd(
                                        search_vector,
                                        websearch_to_tsquery('english', :query),
                                        32
                                    ) AS lexical_rank
                                FROM papers
                                WHERE is_latest_version
                                  AND search_vector @@ websearch_to_tsquery(
                                      'english', :query
                                  )
                            ), ranked AS (
                                SELECT
                                    paper_id,
                                    min(identity_tier) AS identity_tier,
                                    max(lexical_rank) AS lexical_rank
                                FROM candidates
                                GROUP BY paper_id
                            )
                            SELECT p.id
                            FROM papers p
                            JOIN ranked ON ranked.paper_id = p.id
                            ORDER BY
                                ranked.identity_tier,
                                ranked.lexical_rank DESC,
                                p.citation_count DESC,
                                p.date_published DESC NULLS LAST,
                                p.id
                            LIMIT :limit
                        """),
                        {
                            "query": "rotary position embedding",
                            "normalized_title": "rotary position embedding",
                            "limit": limit,
                        },
                    )
                ]
    finally:
        engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["keyword", "semantic", "hybrid"],
        default=["keyword", "semantic", "hybrid"],
    )
    args = parser.parse_args()
    if args.iterations < 1 or args.limit < 1:
        parser.error("--iterations and --limit must be positive")

    report = benchmark(
        args.database_url or get_settings().database_url,
        args.fixture,
        args.iterations,
        args.limit,
        args.modes,
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
