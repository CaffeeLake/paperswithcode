# /// script
# requires-python = ">=3.12"
# ///
"""Score frozen related-paper judgments with source-level bootstrap intervals."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path

from backend.services.embedding_annotation import qc_summary, read_jsonl


CONFIRMATION = "UNBLIND_AND_SCORE"


def dcg(grades: list[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades)
    )


def source_metrics(
    ranked: list[int], judgments: dict[int, int]
) -> dict[str, float | None]:
    top4 = ranked[:4]
    judged4 = [paper_id for paper_id in top4 if paper_id in judgments]
    complete4 = len(judged4) == len(top4) == 4
    grades4 = [judgments[paper_id] for paper_id in top4] if complete4 else []
    ideal = sorted(judgments.values(), reverse=True)[:4]
    relevant = {paper_id for paper_id, grade in judgments.items() if grade > 0}
    judged20 = [paper_id for paper_id in ranked[:20] if paper_id in judgments]
    ideal_dcg = dcg(ideal)
    return {
        "ndcg_at_4": dcg(grades4) / ideal_dcg
        if complete4 and ideal_dcg
        else (0.0 if complete4 else None),
        "graded_precision_at_4": sum(grades4) / 8 if complete4 else None,
        "recall_at_20": len(relevant.intersection(ranked[:20])) / len(relevant)
        if relevant
        else None,
        "top4_coverage": len(judged4) / max(1, len(top4)),
        "top20_coverage": len(judged20) / max(1, len(ranked[:20])),
        "duplicate_rate": 1 - len(set(ranked[:20])) / max(1, len(ranked[:20])),
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def bootstrap(values: list[float], iterations: int, randomizer: random.Random) -> dict:
    if not values:
        return {"mean": None, "ci95_low": None, "ci95_high": None, "n_sources": 0}
    samples = [
        statistics.mean(randomizer.choices(values, k=len(values)))
        for _ in range(iterations)
    ]
    return {
        "mean": statistics.mean(values),
        "ci95_low": percentile(samples, 0.025),
        "ci95_high": percentile(samples, 0.975),
        "n_sources": len(values),
    }


def paired_bootstrap(
    left: dict[int, float],
    right: dict[int, float],
    iterations: int,
    randomizer: random.Random,
) -> dict:
    sources = sorted(set(left) & set(right))
    if not sources:
        return {
            "mean_difference": None,
            "ci95_low": None,
            "ci95_high": None,
            "p_two_sided": None,
            "n_sources": 0,
        }
    differences = [left[source] - right[source] for source in sources]
    samples = [
        statistics.mean(randomizer.choices(differences, k=len(differences)))
        for _ in range(iterations)
    ]
    non_positive = sum(value <= 0 for value in samples) / iterations
    non_negative = sum(value >= 0 for value in samples) / iterations
    return {
        "mean_difference": statistics.mean(differences),
        "ci95_low": percentile(samples, 0.025),
        "ci95_high": percentile(samples, 0.975),
        "p_two_sided": min(1.0, 2 * min(non_positive, non_negative)),
        "n_sources": len(sources),
    }


def load_judgments(path: Path, annotations_path: Path) -> dict[int, dict[int, int]]:
    pairs = {
        row["blind_id"]: (int(row["source_paper_id"]), int(row["candidate_paper_id"]))
        for row in read_jsonl(annotations_path)
    }
    judgments: dict[int, dict[int, int]] = {}
    for row in read_jsonl(path):
        grade = row.get("final_grade")
        if grade is None:
            continue
        if row["blind_id"] not in pairs:
            raise ValueError(f"Unknown blind ID in judgments: {row['blind_id']}")
        source, candidate = pairs[row["blind_id"]]
        judgments.setdefault(source, {})[candidate] = int(grade)
    return judgments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--exports", nargs="*", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(
            f"Refusing to expose system identities without --confirm {CONFIRMATION}"
        )
    judgments = load_judgments(args.judgments, args.annotations)
    randomizer = random.Random(args.seed)
    per_system, configurations = {}, {}
    for path in sorted(args.runs_dir.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        label = run["configuration"]["label"]
        configurations[label] = run["configuration"]
        per_system[label] = {
            int(result["source_paper_id"]): source_metrics(
                [int(value) for value in result["ranked_paper_ids"]],
                judgments[int(result["source_paper_id"])],
            )
            for result in run["results"]
            if int(result["source_paper_id"]) in judgments
        }
    metric_names = [
        "ndcg_at_4",
        "graded_precision_at_4",
        "recall_at_20",
        "duplicate_rate",
        "top4_coverage",
        "top20_coverage",
    ]
    systems = {}
    for label, by_source in per_system.items():
        systems[label] = {"configuration": configurations[label], "metrics": {}}
        for metric in metric_names:
            values = [
                float(row[metric])
                for row in by_source.values()
                if row[metric] is not None
            ]
            systems[label]["metrics"][metric] = bootstrap(
                values, args.bootstrap_iterations, randomizer
            )
    pairwise = []
    labels = sorted(per_system)
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            for metric in ("ndcg_at_4", "graded_precision_at_4", "recall_at_20"):
                left_values = {
                    source: float(values[metric])
                    for source, values in per_system[left].items()
                    if values[metric] is not None
                }
                right_values = {
                    source: float(values[metric])
                    for source, values in per_system[right].items()
                    if values[metric] is not None
                }
                pairwise.append(
                    {
                        "left": left,
                        "right": right,
                        "metric": metric,
                        **paired_bootstrap(
                            left_values,
                            right_values,
                            args.bootstrap_iterations,
                            randomizer,
                        ),
                    }
                )
    valid = sorted(
        (row for row in pairwise if row["p_two_sided"] is not None),
        key=lambda row: row["p_two_sided"],
    )
    running = 0.0
    for rank, row in enumerate(valid):
        running = max(running, min(1.0, row["p_two_sided"] * (len(valid) - rank)))
        row["holm_adjusted_p"] = running
    exported_rows = [row for path in args.exports for row in read_jsonl(path)]
    report = {
        "schema_version": "pwc-related-scoring-v1",
        "judged_sources": len(judgments),
        "bootstrap_iterations": args.bootstrap_iterations,
        "unblinded": True,
        "interpretation": "Unjudged results are excluded from top-4 quality metrics and reported through coverage; Recall@20 is recall within the judged pool, not corpus-wide recall.",
        "annotation_qc": qc_summary(exported_rows) if exported_rows else None,
        "systems": systems,
        "pairwise": pairwise,
    }
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "systems": len(systems),
                "judged_sources": len(judgments),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
