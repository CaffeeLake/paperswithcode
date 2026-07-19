# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy>=2.0",
#   "pyarrow>=18",
# ]
# ///
"""Materialize normalized Matryoshka truncations from one full-vector run."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def materialize(source: Path, destination: Path, dimensions: int) -> dict:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    source_dimensions = int(manifest["dimensions"])
    if manifest.get("status") != "complete":
        raise ValueError("Source embedding run is not complete")
    if not 0 < dimensions < source_dimensions:
        raise ValueError("Target dimensions must be smaller than source dimensions")
    destination.mkdir(parents=True, exist_ok=True)
    shards = []
    norm_min, norm_max = float("inf"), 0.0
    for shard in manifest["shards"]:
        source_path = source / shard["path"]
        if sha256_file(source_path) != shard["sha256"]:
            raise ValueError(f"Source checksum mismatch: {source_path}")
        table = pq.read_table(source_path)
        vectors = np.asarray(table["embedding"].to_pylist(), dtype=np.float32)
        vectors = vectors[:, :dimensions]
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not np.isfinite(vectors).all() or (norms == 0).any():
            raise ValueError(f"Invalid truncated vectors in {source_path}")
        vectors /= norms
        stored = vectors.astype(np.float16)
        stored_norms = np.linalg.norm(stored.astype(np.float32), axis=1)
        norm_min = min(norm_min, float(stored_norms.min()))
        norm_max = max(norm_max, float(stored_norms.max()))
        output_path = destination / shard["path"]
        output = table.set_column(
            table.schema.get_field_index("embedding"),
            "embedding",
            pa.array(stored.tolist(), type=pa.list_(pa.float16(), dimensions)),
        )
        pq.write_table(output, output_path, compression="zstd")
        result = {
            "path": output_path.name,
            "rows": output.num_rows,
            "sha256": sha256_file(output_path),
        }
        (
            destination / output_path.name.replace(".parquet", ".complete.json")
        ).write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
        shards.append(result)
    derived = {
        **manifest,
        "run_id": f"{manifest['run_id']}-d{dimensions}",
        "dimensions": dimensions,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source_full_dimension_run_id": manifest["run_id"],
        "source_full_dimensions": source_dimensions,
        "derivation": "prefix_truncate_then_l2_normalize",
        "norm_min": norm_min,
        "norm_max": norm_max,
        "shards": shards,
    }
    (destination / "manifest.json").write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return derived


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dimensions", type=int, nargs="+", required=True)
    args = parser.parse_args()
    summaries = []
    for dimensions in args.dimensions:
        destination = args.output_root / f"output-{dimensions}d"
        manifest = materialize(args.source, destination, dimensions)
        summaries.append(
            {
                "output": str(destination),
                "dimensions": dimensions,
                "rows": manifest["row_count"],
                "norm_min": manifest["norm_min"],
                "norm_max": manifest["norm_max"],
            }
        )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
