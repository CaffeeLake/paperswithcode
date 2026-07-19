"""Measure exact/HNSW recall, latency, plans, and storage for one generation."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.config import get_settings


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else 0.0


def knn(
    connection,
    generation_id: int,
    dimensions: int,
    vector: str,
    limit: int,
    exact: bool,
):
    connection.execute(text("SET LOCAL enable_seqscan = on"))
    connection.execute(text(f"SET LOCAL enable_indexscan = {'off' if exact else 'on'}"))
    connection.execute(
        text(f"SET LOCAL enable_bitmapscan = {'off' if exact else 'on'}")
    )
    return [
        int(row[0])
        for row in connection.execute(
            text(
                f"""SELECT e.paper_id FROM paper_embeddings e
                     JOIN papers p ON p.id=e.paper_id
                     WHERE e.generation_id=:generation_id AND p.is_latest_version
                     ORDER BY e.embedding::halfvec({dimensions}) <=>
                              CAST(:vector AS halfvec({dimensions}))
                     LIMIT :limit"""
            ),
            {"generation_id": generation_id, "vector": vector, "limit": limit},
        )
    ]


def benchmark(
    database_url: str, generation_id: int, sample_size: int, limit: int, seed: int
):
    engine = create_engine(database_url)
    randomizer = random.Random(seed)
    try:
        with engine.connect() as connection:
            generation = (
                connection.execute(
                    text(
                        """SELECT model_name, model_revision, dimensions, input_format_version
                       FROM paper_embedding_generations WHERE id=:id"""
                    ),
                    {"id": generation_id},
                )
                .mappings()
                .one()
            )
            population = connection.execute(
                text(
                    """SELECT e.paper_id, e.embedding::text FROM paper_embeddings e
                       JOIN papers p ON p.id=e.paper_id
                       WHERE e.generation_id=:id AND p.is_latest_version"""
                ),
                {"id": generation_id},
            ).all()
            samples = randomizer.sample(population, min(sample_size, len(population)))
            recalls, exact_ms, hnsw_ms = [], [], []
            for _, vector in samples:
                with connection.begin_nested():
                    started = time.perf_counter()
                    exact_ids = knn(
                        connection,
                        generation_id,
                        generation["dimensions"],
                        vector,
                        limit,
                        True,
                    )
                    exact_ms.append((time.perf_counter() - started) * 1000)
                with connection.begin_nested():
                    started = time.perf_counter()
                    hnsw_ids = knn(
                        connection,
                        generation_id,
                        generation["dimensions"],
                        vector,
                        limit,
                        False,
                    )
                    hnsw_ms.append((time.perf_counter() - started) * 1000)
                recalls.append(len(set(exact_ids) & set(hnsw_ids)) / len(exact_ids))

            partition = f"paper_embeddings_g{generation_id}"
            sizes = (
                connection.execute(
                    text(
                        """SELECT pg_total_relation_size(:partition) AS total_bytes,
                              pg_relation_size(:partition) AS table_bytes,
                              pg_indexes_size(:partition) AS index_bytes"""
                    ),
                    {"partition": partition},
                )
                .mappings()
                .one()
            )
            plan = []
            if samples:
                plan = [
                    row[0]
                    for row in connection.execute(
                        text(
                            f"""EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                               SELECT e.paper_id FROM paper_embeddings e JOIN papers p ON p.id=e.paper_id
                               WHERE e.generation_id=:generation_id AND p.is_latest_version
                               ORDER BY e.embedding::halfvec({generation["dimensions"]}) <=>
                                        CAST(:vector AS halfvec({generation["dimensions"]}))
                               LIMIT :limit"""
                        ),
                        {
                            "generation_id": generation_id,
                            "vector": samples[0][1],
                            "limit": limit,
                        },
                    )
                ]
        return {
            "generation_id": generation_id,
            "generation": dict(generation),
            "sample_size": len(samples),
            "k": limit,
            "recall_at_k": statistics.fmean(recalls) if recalls else None,
            "exact_latency_ms": {
                "p50": percentile(exact_ms, 0.5),
                "p95": percentile(exact_ms, 0.95),
            },
            "hnsw_latency_ms": {
                "p50": percentile(hnsw_ms, 0.5),
                "p95": percentile(hnsw_ms, 0.95),
            },
            "storage": dict(sizes),
            "plan": plan,
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation_id", type=int)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(
        args.database_url or get_settings().database_url,
        args.generation_id,
        args.sample_size,
        args.limit,
        args.seed,
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
