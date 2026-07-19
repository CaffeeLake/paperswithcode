"""Export or validate immutable paper-summary generation artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.database.connection import db_manager
from backend.services.embedding_contracts import sha256_file
from backend.services.paper_summary_pipeline import (
    MANIFEST_SCHEMA_VERSION,
    configure_summary_snapshot,
    count_words,
    export_summary_snapshot,
    select_representative_paper_ids,
    summary_word_bounds,
    summary_input_hash,
    validate_summary,
)


def validate_run(input_dir: Path, output_dir: Path) -> dict[str, object]:
    source = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    final = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if source["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported input manifest schema")
    for key in ("run_id", "row_count", "corpus_snapshot"):
        if final.get(key) != source.get(key):
            raise ValueError(f"Output manifest mismatch for {key}")
    consolidated = bool(final.get("selection_policy"))
    if consolidated:
        if final.get("ordered_paper_ids_sha256") != source.get(
            "ordered_paper_ids_sha256"
        ):
            raise ValueError("Consolidated output ordered-ID hash mismatch")
        if final.get("input_shard_sha256") != source["shards"][0]["sha256"]:
            raise ValueError("Consolidated output input-shard hash mismatch")
        allowed_model_revisions = {
            (entry["model"], entry["revision"]) for entry in final["model_revisions"]
        }
        candidate_manifests = final["candidate_manifest_sha256"]
    else:
        if final.get("prompt_hash") != source.get("prompt_hash"):
            raise ValueError("Output manifest mismatch for prompt_hash")
    input_rows: dict[int, dict] = {}
    for shard in source["shards"]:
        path = input_dir / shard["path"]
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"Input checksum mismatch: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            paper_id = int(row["paper_id"])
            if paper_id in input_rows:
                raise ValueError(f"Duplicate input paper ID: {paper_id}")
            if row["input_hash"] != summary_input_hash(row["title"], row["abstract"]):
                raise ValueError(f"Input hash mismatch: {paper_id}")
            input_rows[paper_id] = row
    output_rows: dict[int, dict] = {}
    for shard in final["shards"]:
        path = output_dir / shard["path"]
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"Output checksum mismatch: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            paper_id = int(row["paper_id"])
            if paper_id in output_rows:
                raise ValueError(f"Duplicate output paper ID: {paper_id}")
            source_row = input_rows.get(paper_id)
            if source_row is None or row["input_hash"] != source_row["input_hash"]:
                raise ValueError(f"Output source mismatch: {paper_id}")
            if consolidated:
                if (
                    row.get("model"),
                    row.get("revision"),
                ) not in allowed_model_revisions:
                    raise ValueError(f"Unlisted model provenance: {paper_id}")
                if not row.get("prompt_version") or not row.get("prompt_hash"):
                    raise ValueError(f"Missing prompt provenance: {paper_id}")
                if not isinstance(row.get("generation_parameters"), dict):
                    raise ValueError(f"Missing generation parameters: {paper_id}")
                selection_source = row.get("selection_source")
                if row.get("source_manifest_sha256") != candidate_manifests.get(
                    selection_source
                ):
                    raise ValueError(
                        f"Candidate manifest provenance mismatch: {paper_id}"
                    )
            expected_errors = validate_summary(
                row.get("summary", ""), abstract=source_row["abstract"]
            )
            if row.get("validation_errors") != expected_errors:
                raise ValueError(f"Validation mismatch: {paper_id}")
            if consolidated:
                minimum_words, maximum_words = summary_word_bounds(
                    source_row["abstract"]
                )
                expected_bounds = {
                    "source_abstract_word_count": count_words(source_row["abstract"]),
                    "effective_min_words": minimum_words,
                    "effective_max_words": maximum_words,
                }
                if any(row.get(key) != value for key, value in expected_bounds.items()):
                    raise ValueError(
                        f"Validation-bound provenance mismatch: {paper_id}"
                    )
            expected_status = (
                "valid" if not expected_errors and not row.get("error") else "invalid"
            )
            if row.get("validation_status") != expected_status:
                raise ValueError(f"Validation status mismatch: {paper_id}")
            output_rows[paper_id] = row
    if list(input_rows) != list(output_rows):
        raise ValueError("Output paper order or coverage differs from input")
    report = {
        "status": "valid",
        "row_count": len(output_rows),
        "valid_count": sum(
            row["validation_status"] == "valid" for row in output_rows.values()
        ),
        "invalid_count": sum(
            row["validation_status"] != "valid" for row in output_rows.values()
        ),
        "input_manifest_sha256": sha256_file(input_dir / "manifest.json"),
        "output_manifest_sha256": sha256_file(output_dir / "manifest.json"),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--output-root", type=Path, required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--shard-rows", type=int, default=2_000)
    export.add_argument("--paper-id", type=int, action="append")
    export.add_argument("--representative-size", type=int)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        with db_manager.session_local() as db:
            paper_ids = args.paper_id
            snapshot_configured = False
            if args.representative_size is not None:
                configure_summary_snapshot(db)
                snapshot_configured = True
                paper_ids = select_representative_paper_ids(
                    db,
                    forced_ids=args.paper_id or [],
                    size=args.representative_size,
                )
            result = export_summary_snapshot(
                db,
                args.output_root,
                run_id=args.run_id,
                shard_rows=args.shard_rows,
                paper_ids=paper_ids,
                snapshot_configured=snapshot_configured,
            )
        print(json.dumps(result.manifest, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(validate_run(args.input, args.output), indent=2, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
