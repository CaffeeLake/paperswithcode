"""Build exact-neighbor run files from completed embedding Parquet artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def load_artifacts(output_dir: Path, dimensions: int | None):
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Output manifest is not complete")
    ids, chunks = [], []
    for shard in manifest["shards"]:
        table = pq.read_table(
            output_dir / shard["path"], columns=["paper_id", "embedding"]
        )
        ids.extend(int(value) for value in table["paper_id"].to_pylist())
        chunks.append(np.asarray(table["embedding"].to_pylist(), dtype=np.float32))
    vectors = (
        np.concatenate(chunks) if chunks else np.empty((0, manifest["dimensions"]))
    )
    requested = dimensions or manifest["dimensions"]
    if requested != manifest["dimensions"]:
        if requested > manifest["dimensions"]:
            raise ValueError("Requested dimensions exceed stored dimensions")
        vectors = vectors[:, :requested]
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return manifest, np.asarray(ids, dtype=np.int64), vectors, requested


def exact_neighbors(
    ids: np.ndarray, vectors: np.ndarray, source_ids: list[int], k: int
):
    positions = {int(paper_id): index for index, paper_id in enumerate(ids)}
    results = []
    for source_id in source_ids:
        position = positions.get(source_id)
        if position is None:
            continue
        scores = vectors @ vectors[position]
        scores[position] = -np.inf
        count = min(k, max(0, len(scores) - 1))
        indices = (
            np.argpartition(-scores, count - 1)[:count]
            if count
            else np.array([], dtype=int)
        )
        indices = indices[np.argsort(-scores[indices])]
        results.append(
            {
                "source_paper_id": source_id,
                "ranked_paper_ids": [int(ids[index]) for index in indices],
                "scores": [float(scores[index]) for index in indices],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--k", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest, ids, vectors, dimensions = load_artifacts(
        args.output_dir, args.dimensions
    )
    source_payload = json.loads(args.sources.read_text(encoding="utf-8"))
    source_ids = sorted(
        {int(item["source_paper_id"]) for item in source_payload["judgments"]}
    )
    run = {
        "configuration": {
            "run_id": manifest["run_id"],
            "model_name": manifest["model_name"],
            "model_revision": manifest["model_revision"],
            "dimensions": dimensions,
            "input_format_version": manifest["input_format_version"],
            "corpus_snapshot": manifest["corpus_snapshot"],
            "retrieval": "exact_cosine",
        },
        "results": exact_neighbors(ids, vectors, source_ids, args.k),
    }
    args.output.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(run["configuration"], indent=2))


if __name__ == "__main__":
    main()
