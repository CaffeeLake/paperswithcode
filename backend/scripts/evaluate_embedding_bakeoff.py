"""Evaluate pooled related/search retrieval runs with reproducible IR metrics.

Each run file is JSON with ``configuration`` metadata and ``results`` entries:
``{"source_paper_id"|"query": ..., "ranked_paper_ids": [...]}``.
The script can also emit a blinded, deduplicated annotation pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def dcg(grades: list[int], cutoff: int) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(grades[:cutoff], 1)
    )


def evaluate_related(judgments: dict, results: list[dict]) -> dict[str, float]:
    by_source: dict[int, dict[int, int]] = defaultdict(dict)
    for item in judgments["judgments"]:
        by_source[int(item["source_paper_id"])][int(item["related_paper_id"])] = item[
            "grade"
        ]
    ndcgs, precisions, recalls, duplicate_rates = [], [], [], []
    for result in results:
        relevant = by_source.get(int(result["source_paper_id"]), {})
        if not relevant:
            continue
        ranked = [int(paper_id) for paper_id in result["ranked_paper_ids"]]
        top = ranked[:4]
        grades = [relevant.get(paper_id, 0) for paper_id in top]
        ideal = dcg(sorted(relevant.values(), reverse=True), 4)
        ndcgs.append(dcg(grades, 4) / ideal if ideal else 0.0)
        precisions.append(sum(grade / 2 for grade in grades) / 4)
        recalls.append(len(set(ranked[:20]) & relevant.keys()) / len(relevant))
        duplicate_rates.append(1 - len(set(top)) / len(top) if top else 0.0)

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "ndcg_at_4": mean(ndcgs),
        "graded_precision_at_4": mean(precisions),
        "recall_at_20": mean(recalls),
        "duplicate_rate_at_4": mean(duplicate_rates),
        "evaluated_sources": len(ndcgs),
    }


def blinded_pool(runs: list[dict], seed: int) -> list[dict]:
    candidates: dict[int, set[int]] = defaultdict(set)
    for run in runs:
        for result in run["results"]:
            candidates[int(result["source_paper_id"])].update(
                int(paper_id) for paper_id in result["ranked_paper_ids"]
            )
    randomizer = random.Random(seed)
    pool = []
    for source, related in sorted(candidates.items()):
        related = list(related)
        randomizer.shuffle(related)
        for candidate in related:
            blind_id = hashlib.sha256(
                f"{seed}:{source}:{candidate}".encode()
            ).hexdigest()[:16]
            pool.append(
                {
                    "blind_id": blind_id,
                    "source_paper_id": source,
                    "candidate_paper_id": candidate,
                    "grade": None,
                }
            )
    return pool


def load_judgments(
    local_path: Path | None,
    dataset_id: str | None,
    revision: str | None,
    split: str,
) -> dict:
    if local_path:
        return json.loads(local_path.read_text(encoding="utf-8"))
    if not dataset_id or not revision:
        raise ValueError("HF judgments require both dataset ID and pinned revision")
    from datasets import load_dataset

    dataset = load_dataset(
        dataset_id,
        "related_papers_relevance",
        revision=revision,
        split=split,
    )
    return {
        "schema_version": "related-papers-relevance-v1",
        "corpus_snapshot": dataset.info.description or "declared-in-dataset-card",
        "dataset_id": dataset_id,
        "dataset_revision": revision,
        "judgments": [dict(row) for row in dataset],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    judgment_source = parser.add_mutually_exclusive_group(required=True)
    judgment_source.add_argument("--judgments", type=Path)
    judgment_source.add_argument("--judgments-dataset")
    parser.add_argument("--dataset-revision")
    parser.add_argument("--dataset-split", default="test")
    parser.add_argument("--blinded-pool", type=Path)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    judgments = load_judgments(
        args.judgments,
        args.judgments_dataset,
        args.dataset_revision,
        args.dataset_split,
    )
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.runs]
    report = {
        "judgment_schema": judgments["schema_version"],
        "corpus_snapshot": judgments["corpus_snapshot"],
        "runs": [
            {
                "configuration": run["configuration"],
                "metrics": evaluate_related(judgments, run["results"]),
            }
            for run in runs
        ],
    }
    if args.blinded_pool:
        args.blinded_pool.write_text(
            json.dumps(blinded_pool(runs, args.seed), indent=2) + "\n",
            encoding="utf-8",
        )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
