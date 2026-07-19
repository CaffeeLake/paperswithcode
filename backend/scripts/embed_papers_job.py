# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy>=2.0",
#   "pyarrow>=18",
#   "sentence-transformers>=5.0",
#   "torch>=2.5",
# ]
# ///
"""Restartable Hugging Face Jobs worker for paper document embeddings."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from sentence_transformers import SentenceTransformer


SCHEMA_VERSION = "paper-embeddings-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path, args: argparse.Namespace) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version": SCHEMA_VERSION}
    if not args.reuse_snapshot:
        expected.update(
            model_name=args.model,
            model_revision=args.revision,
            dimensions=args.dimensions,
        )
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Manifest {key}={manifest.get(key)!r}, expected {value!r}"
            )
    for shard in manifest["shards"]:
        input_path = path.parent / shard["path"]
        if sha256_file(input_path) != shard["sha256"]:
            raise ValueError(f"Input checksum mismatch: {input_path}")
    return manifest


def valid_completed_shard(path: Path, marker: Path, expected_rows: int) -> bool:
    if not path.is_file() or not marker.is_file():
        return False
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    return metadata.get("rows") == expected_rows and metadata.get(
        "sha256"
    ) == sha256_file(path)


def validate_vectors(vectors: np.ndarray, dimensions: int) -> None:
    if vectors.ndim != 2 or vectors.shape[1] != dimensions:
        raise ValueError(f"Wrong output shape: {vectors.shape}")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding output contains NaN or infinity")
    norms = np.linalg.norm(vectors.astype(np.float32), axis=1)
    if len(norms) and (float(norms.min()) < 0.98 or float(norms.max()) > 1.02):
        raise ValueError(
            f"Abnormal normalized-vector norms: {norms.min():.6f}..{norms.max():.6f}"
        )


def read_records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def encode_shard(
    model, records: list[dict], args: argparse.Namespace
) -> tuple[np.ndarray, int, int]:
    ordered = sorted(
        enumerate(records), key=lambda item: len(item[1]["embedding_input"])
    )
    texts = [record["embedding_input"] for _, record in ordered]
    tokenized = model.tokenizer(texts, truncation=True, padding=False)
    lengths = [len(ids) for ids in tokenized["input_ids"]]
    non_padding_tokens = sum(lengths)
    padded_tokens = sum(
        max(lengths[start : start + args.batch_size], default=0)
        * len(lengths[start : start + args.batch_size])
        for start in range(0, len(lengths), args.batch_size)
    )
    batch_size = args.batch_size
    while True:
        try:
            with torch.inference_mode():
                vectors = model.encode_document(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=True,
                )
            break
        except torch.OutOfMemoryError:
            if batch_size == 1:
                raise
            batch_size = max(1, batch_size // 2)
            torch.cuda.empty_cache()
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.shape[1] != args.dimensions:
        if not args.allow_matryoshka:
            raise ValueError(
                "Refusing unadvertised dimensional truncation; pass --allow-matryoshka "
                "only for a model/configuration that supports it"
            )
        vectors = vectors[:, : args.dimensions]
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    restored = np.empty_like(vectors)
    for ordered_index, (original_index, _) in enumerate(ordered):
        restored[original_index] = vectors[ordered_index]
    validate_vectors(restored, args.dimensions)
    return restored.astype(np.float16), non_padding_tokens, padded_tokens


def write_atomic_parquet(path: Path, records: list[dict], vectors: np.ndarray) -> dict:
    temporary = path.with_suffix(path.suffix + ".tmp")
    table = pa.table(
        {
            "paper_id": pa.array([row["paper_id"] for row in records], pa.int64()),
            "content_hash": pa.array([row["content_hash"] for row in records]),
            "embedding": pa.array(
                vectors.tolist(), type=pa.list_(pa.float16(), vectors.shape[1])
            ),
        }
    )
    pq.write_table(table, temporary, compression="zstd")
    reread = pq.read_table(temporary)
    if reread.num_rows != len(records):
        raise ValueError(f"Parquet validation failed for {temporary}")
    temporary.replace(path)
    return {"path": path.name, "rows": len(records), "sha256": sha256_file(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dimensions", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--allow-matryoshka", action="store_true")
    parser.add_argument(
        "--reuse-snapshot",
        action="store_true",
        help=(
            "Reuse checksummed input shards exported for another model while "
            "recording this job's pinned model metadata in the output manifest"
        ),
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(args.input / "manifest.json", args)
    started = time.monotonic()
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = SentenceTransformer(
        args.model,
        revision=args.revision,
        trust_remote_code=True,
        model_kwargs={"torch_dtype": dtype},
    )
    startup_seconds = time.monotonic() - started
    output_shards = []
    paper_ids: set[int] = set()
    non_padding_tokens = 0
    padded_tokens = 0
    for index, shard in enumerate(manifest["shards"]):
        records = read_records(args.input / shard["path"])
        ids = {int(record["paper_id"]) for record in records}
        if len(ids) != len(records) or ids.intersection(paper_ids):
            raise ValueError("Duplicate paper IDs in input")
        paper_ids.update(ids)
        output_path = args.output / f"embeddings-{index:05d}.parquet"
        marker = output_path.with_suffix(".complete.json")
        if valid_completed_shard(output_path, marker, len(records)):
            completed = json.loads(marker.read_text(encoding="utf-8"))
            non_padding_tokens += completed.get("non_padding_tokens", 0)
            padded_tokens += completed.get("padded_tokens", 0)
            output_shards.append(completed)
            continue
        vectors, shard_tokens, shard_padded_tokens = encode_shard(model, records, args)
        non_padding_tokens += shard_tokens
        padded_tokens += shard_padded_tokens
        result = write_atomic_parquet(output_path, records, vectors)
        result["non_padding_tokens"] = shard_tokens
        result["padded_tokens"] = shard_padded_tokens
        marker_tmp = marker.with_suffix(marker.suffix + ".tmp")
        marker_tmp.write_text(
            json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
        )
        marker_tmp.replace(marker)
        output_shards.append(result)

    if len(paper_ids) != manifest["row_count"]:
        raise ValueError("Input manifest row coverage mismatch")
    duration_seconds = time.monotonic() - started
    final = {
        **{
            key: manifest[key]
            for key in (
                "schema_version",
                "input_format_version",
                "normalization",
                "query_instruction_version",
                "corpus_snapshot",
            )
        },
        "run_id": args.output.parent.name,
        "model_name": args.model,
        "model_revision": args.revision,
        "dimensions": args.dimensions,
        "source_snapshot_run_id": manifest["run_id"],
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(paper_ids),
        "dtype": "float16",
        "duration_seconds": duration_seconds,
        "startup_seconds": startup_seconds,
        "papers_per_second": len(paper_ids) / duration_seconds
        if duration_seconds
        else None,
        "non_padding_tokens": non_padding_tokens,
        "non_padding_tokens_per_second": non_padding_tokens / duration_seconds
        if duration_seconds
        else None,
        "padded_tokens": padded_tokens,
        "padded_tokens_per_second": padded_tokens / duration_seconds
        if duration_seconds
        else None,
        "hardware": {
            "hostname": platform.node(),
            "cuda": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "peak_vram_bytes": torch.cuda.max_memory_allocated()
            if torch.cuda.is_available()
            else 0,
            "gpu_utilization_percent": None,
        },
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("sentence-transformers", "torch", "numpy", "pyarrow")
        },
        "shards": output_shards,
    }
    temporary = args.output / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output / "manifest.json")
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
