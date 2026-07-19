# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy>=2.0",
#   "pyarrow>=18",
#   "scikit-learn>=1.6",
# ]
# ///
"""Build a blinded, stratified local annotation package for embedding bakeoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.scripts.build_embedding_bakeoff_run import exact_neighbors, load_artifacts


def read_snapshot(input_dir: Path) -> tuple[dict[int, dict], list[int]]:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    records, ordered_ids = {}, []
    for shard in manifest["shards"]:
        for line in (
            (input_dir / shard["path"]).read_text(encoding="utf-8").splitlines()
        ):
            record = json.loads(line)
            paper_id = int(record["paper_id"])
            records[paper_id] = record
            ordered_ids.append(paper_id)
    if len(ordered_ids) != manifest["row_count"] or len(records) != len(ordered_ids):
        raise ValueError("Snapshot row coverage is invalid")
    return records, ordered_ids


def stratified_sources(records: dict[int, dict], count: int, seed: int) -> list[dict]:
    ordered = sorted(
        records.values(), key=lambda row: (len(row["embedding_input"]), row["paper_id"])
    )
    strata = 5
    randomizer = random.Random(seed)
    selected = []
    for index in range(strata):
        start = len(ordered) * index // strata
        end = len(ordered) * (index + 1) // strata
        group = ordered[start:end]
        target = count // strata + (1 if index < count % strata else 0)
        for row in randomizer.sample(group, min(target, len(group))):
            selected.append(
                {
                    "source_paper_id": int(row["paper_id"]),
                    "stratum": f"document_length_q{index + 1}",
                    "document_characters": len(row["embedding_input"]),
                }
            )
    return sorted(selected, key=lambda item: item["source_paper_id"])


def ranked(
    ids: np.ndarray, scores: np.ndarray, source_position: int, k: int
) -> list[int]:
    scores = np.asarray(scores).reshape(-1)
    scores[source_position] = -np.inf
    count = min(k, len(scores) - 1)
    positions = np.argpartition(-scores, count - 1)[:count]
    positions = positions[np.argsort(-scores[positions])]
    return [int(ids[position]) for position in positions]


def lexical_run(
    records: dict[int, dict], ordered_ids: list[int], sources: list[int], k: int
) -> dict:
    texts = [records[paper_id]["embedding_input"] for paper_id in ordered_ids]
    matrix = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_features=50_000,
        sublinear_tf=True,
    ).fit_transform(texts)
    ids = np.asarray(ordered_ids, dtype=np.int64)
    positions = {paper_id: index for index, paper_id in enumerate(ordered_ids)}
    results = []
    for source in sources:
        position = positions[source]
        scores = (matrix @ matrix[position].T).toarray()[:, 0]
        results.append(
            {
                "source_paper_id": source,
                "ranked_paper_ids": ranked(ids, scores, position, k),
            }
        )
    return {
        "configuration": {
            "label": "keyword_tfidf",
            "retrieval": "tfidf_english_1_2gram",
        },
        "results": results,
    }


def dense_run(spec: dict, sources: list[int], k: int) -> dict:
    manifest, ids, vectors, dimensions = load_artifacts(
        Path(spec["output_dir"]), spec.get("dimensions")
    )
    return {
        "configuration": {
            "label": spec["label"],
            "retrieval": "exact_cosine",
            "model_name": manifest["model_name"],
            "model_revision": manifest["model_revision"],
            "dimensions": dimensions,
            "run_id": manifest["run_id"],
        },
        "results": exact_neighbors(ids, vectors, sources, k),
    }


def hybrid_run(keyword: dict, dense: dict, k: int, rrf_k: int = 60) -> dict:
    keyword_by_source = {item["source_paper_id"]: item for item in keyword["results"]}
    results = []
    for dense_result in dense["results"]:
        source = dense_result["source_paper_id"]
        scores = defaultdict(float)
        for run_result in (keyword_by_source[source], dense_result):
            for rank, paper_id in enumerate(run_result["ranked_paper_ids"], 1):
                scores[int(paper_id)] += 1 / (rrf_k + rank)
        ranked_ids = sorted(scores, key=lambda paper_id: (-scores[paper_id], paper_id))[
            :k
        ]
        results.append({"source_paper_id": source, "ranked_paper_ids": ranked_ids})
    return {
        "configuration": {
            "label": f"hybrid_rrf__{dense['configuration']['label']}",
            "retrieval": "rrf",
            "rrf_k": rrf_k,
        },
        "results": results,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--runs-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-count", type=int, default=100)
    parser.add_argument("--retrieval-depth", type=int, default=20)
    parser.add_argument("--pool-depth", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()

    records, ordered_ids = read_snapshot(args.input)
    selected = stratified_sources(records, args.source_count, args.seed)
    source_ids = [item["source_paper_id"] for item in selected]
    keyword = lexical_run(records, ordered_ids, source_ids, args.retrieval_depth)
    specs = json.loads(args.runs_spec.read_text(encoding="utf-8"))
    dense = [dense_run(spec, source_ids, args.retrieval_depth) for spec in specs]
    runs = [
        keyword,
        *dense,
        *(hybrid_run(keyword, run, args.retrieval_depth) for run in dense),
    ]

    args.output.mkdir(parents=True, exist_ok=True)
    runs_dir = args.output / "runs"
    runs_dir.mkdir(exist_ok=True)
    for run in runs:
        (runs_dir / f"{run['configuration']['label']}.json").write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    provenance = defaultdict(list)
    for run in runs:
        label = run["configuration"]["label"]
        for result in run["results"]:
            source = int(result["source_paper_id"])
            for rank, candidate in enumerate(
                result["ranked_paper_ids"][: args.pool_depth], 1
            ):
                provenance[(source, int(candidate))].append(
                    {"system": label, "rank": rank}
                )
    strata = {item["source_paper_id"]: item for item in selected}
    grouped = defaultdict(list)
    for source, candidate in provenance:
        grouped[source].append(candidate)
    randomizer = random.Random(args.seed)
    annotations, provenance_rows = [], []
    for source in sorted(grouped):
        candidates = grouped[source]
        randomizer.shuffle(candidates)
        for display_order, candidate in enumerate(candidates, 1):
            blind_id = hashlib.sha256(
                f"{args.seed}:{source}:{candidate}".encode()
            ).hexdigest()[:16]
            annotations.append(
                {
                    "blind_id": blind_id,
                    "source_paper_id": source,
                    "source_title": records[source]["title"],
                    "source_abstract": records[source]["abstract"],
                    "candidate_paper_id": candidate,
                    "candidate_title": records[candidate]["title"],
                    "candidate_abstract": records[candidate]["abstract"],
                    "source_stratum": strata[source]["stratum"],
                    "display_order": display_order,
                    "grade": None,
                    "notes": None,
                }
            )
            provenance_rows.append(
                {"blind_id": blind_id, "systems": provenance[(source, candidate)]}
            )
    write_jsonl(args.output / "annotations.jsonl", annotations)
    write_jsonl(args.output / "provenance.jsonl", provenance_rows)
    write_jsonl(args.output / "sources.jsonl", selected)
    schema = {
        "features": {
            "blind_id": {"dtype": "string", "_type": "Value"},
            "source_paper_id": {"dtype": "int64", "_type": "Value"},
            "source_title": {"dtype": "string", "_type": "Value"},
            "source_abstract": {"dtype": "string", "_type": "Value"},
            "candidate_paper_id": {"dtype": "int64", "_type": "Value"},
            "candidate_title": {"dtype": "string", "_type": "Value"},
            "candidate_abstract": {"dtype": "string", "_type": "Value"},
            "source_stratum": {"dtype": "string", "_type": "Value"},
            "display_order": {"dtype": "int32", "_type": "Value"},
            "grade": {"dtype": "int8", "_type": "Value"},
            "notes": {"dtype": "string", "_type": "Value"},
        }
    }
    (args.output / "dataset_info.json").write_text(
        json.dumps({"default": schema}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    instructions = """# Related-paper bakeoff annotation\n\nJudge each candidate using only the source and candidate text; system identities are withheld.\n\n- **2 (highly related):** same problem, method family, benchmark, or a direct extension/comparison.\n- **1 (somewhat related):** useful topical or methodological connection, but not a close substitute.\n- **0 (not related):** superficial keyword overlap or no meaningful research connection.\n\nAssign one grade per row. Use `notes` only for ambiguity, duplicates, language issues, or suspected paper-version leakage. Do not infer relevance from numeric paper IDs. Annotate all candidates for a source together before moving to the next source. `provenance.jsonl` must remain hidden until judgments are frozen.\n"""
    (args.output / "README.md").write_text(instructions, encoding="utf-8")
    summary = {
        "schema_version": "related-papers-bakeoff-annotation-v1",
        "seed": args.seed,
        "source_count": len(selected),
        "pair_count": len(annotations),
        "pool_depth_per_system": args.pool_depth,
        "systems": [run["configuration"] for run in runs],
        "strata": dict(
            sorted(
                (name, sum(s["stratum"] == name for s in selected))
                for name in {s["stratum"] for s in selected}
            )
        ),
    }
    (args.output / "package_manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
