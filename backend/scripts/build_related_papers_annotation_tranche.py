# /// script
# requires-python = ">=3.12"
# ///
"""Create a balanced first-pass tranche and weak/silver diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.services.embedding_annotation import (
    build_first_pass,
    read_jsonl,
    silver_diagnostics,
    write_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-count", type=int, default=20)
    parser.add_argument(
        "--pairs-per-source", type=int, default=0, help="0 keeps every pooled candidate"
    )
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()
    manifest = build_first_pass(
        args.package,
        args.output,
        source_count=args.source_count,
        pairs_per_source=args.pairs_per_source,
        seed=args.seed,
    )
    write_jsonl(
        args.output / "silver_diagnostics.jsonl",
        silver_diagnostics(read_jsonl(args.package / "annotations.jsonl")),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
