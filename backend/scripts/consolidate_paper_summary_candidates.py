"""Consolidate immutable outputs from one model into one validated artifact."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.services.paper_summary_pipeline import (
    MANIFEST_SCHEMA_VERSION,
    count_words,
    sha256_file,
    strip_model_meta_postamble,
    summary_word_bounds,
    validate_summary,
)


SELECTION_POLICY = "first-valid-then-strip-model-meta-postamble-v1"


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def write_jsonl_atomic(path: Path, rows: list[dict]) -> str:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)
    return sha256_file(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-mixed-models", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty output: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)
    source = json.loads((args.input / "manifest.json").read_text(encoding="utf-8"))
    input_rows = []
    for shard in source["shards"]:
        path = args.input / shard["path"]
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"Input checksum mismatch: {path}")
        input_rows.extend(read_jsonl(path))
    input_by_id = {row["paper_id"]: row for row in input_rows}

    candidates = []
    model = revision = None
    model_revisions: set[tuple[str, str]] = set()
    for directory in args.candidate:
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        shard = manifest["shards"][0]
        output_path = directory / shard["path"]
        if sha256_file(output_path) != shard["sha256"]:
            raise ValueError(f"Candidate checksum mismatch: {output_path}")
        rows = read_jsonl(output_path)
        candidate_ids = [row["paper_id"] for row in rows]
        if candidate_ids != sorted(candidate_ids) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError(f"Candidate IDs are not unique and ordered: {directory}")
        if any(paper_id not in input_by_id for paper_id in candidate_ids):
            raise ValueError(f"Candidate contains an ID outside the input: {directory}")
        if any(
            row["input_hash"] != input_by_id[row["paper_id"]]["input_hash"]
            for row in rows
        ):
            raise ValueError(f"Candidate input hashes differ: {directory}")
        model = model or manifest["model"]
        revision = revision or manifest["revision"]
        model_revisions.add((manifest["model"], manifest["revision"]))
        if not args.allow_mixed_models and (
            manifest["model"],
            manifest["revision"],
        ) != (model, revision):
            raise ValueError("Candidates must use one model and revision")
        source_name = (
            directory.parent.name if directory.name == "output" else directory.name
        )
        candidates.append(
            (
                source_name,
                directory,
                manifest,
                {row["paper_id"]: row for row in rows},
                sha256_file(manifest_path),
            )
        )

    selected = []
    source_counts: Counter[str] = Counter()
    normalized_count = 0
    for input_row in input_rows:
        choice = None
        for source_name, _directory, _manifest, rows, manifest_sha256 in candidates:
            row = rows.get(input_row["paper_id"])
            if row is None:
                continue
            summary = row["summary"].strip()
            normalization = None
            if validate_summary(summary, abstract=input_row["abstract"]):
                normalized = strip_model_meta_postamble(summary)
                if validate_summary(normalized, abstract=input_row["abstract"]):
                    continue
                summary = normalized
                normalization = "strip-model-meta-postamble-v1"
            minimum_words, maximum_words = summary_word_bounds(input_row["abstract"])
            choice = {
                **row,
                "summary": summary,
                "validation_status": "valid",
                "validation_errors": [],
                "selection_source": source_name,
                "source_manifest_sha256": manifest_sha256,
                "normalization": normalization,
                "source_abstract_word_count": count_words(input_row["abstract"]),
                "effective_min_words": minimum_words,
                "effective_max_words": maximum_words,
            }
            source_counts[source_name] += 1
            normalized_count += normalization is not None
            break
        if choice is None:
            raise ValueError(
                f"No valid same-model summary for paper {input_row['paper_id']}"
            )
        selected.append(choice)

    output_path = args.output / "summaries-00000.jsonl"
    output_sha256 = write_jsonl_atomic(output_path, selected)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "run_id": source["run_id"],
        "corpus_snapshot": source["corpus_snapshot"],
        "snapshot_time": source["snapshot_time"],
        "row_count": len(selected),
        "valid_count": len(selected),
        "invalid_count": 0,
        "error_count": 0,
        "ordered_paper_ids_sha256": source["ordered_paper_ids_sha256"],
        "input_shard_sha256": source["shards"][0]["sha256"],
        "model": model if len(model_revisions) == 1 else "mixed",
        "revision": revision if len(model_revisions) == 1 else None,
        "model_revisions": [
            {"model": candidate_model, "revision": candidate_revision}
            for candidate_model, candidate_revision in sorted(model_revisions)
        ],
        "selection_policy": SELECTION_POLICY,
        "validation_policy": {
            "name": "source-aware-summary-length-v1",
            "normal_min_words": 80,
            "short_source_abstract_words_below": 100,
            "short_source_min_formula": "min(80, max(30, ceil(0.75 * abstract_words)))",
            "max_words": 120,
        },
        "selection_source_counts": dict(sorted(source_counts.items())),
        "normalized_count": normalized_count,
        "candidate_manifest_sha256": {
            source_name: manifest_sha256
            for source_name, _, _, _, manifest_sha256 in candidates
        },
        "shards": [
            {"path": output_path.name, "rows": len(selected), "sha256": output_sha256}
        ],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
