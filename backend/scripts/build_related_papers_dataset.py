# /// script
# requires-python = ">=3.12"
# ///
"""Assemble the canonical private related-paper judgment Dataset directory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from backend.services.embedding_annotation import sha256_file, validate_package


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--tranche", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package_summary = validate_package(args.package)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError(
            "Output directory must be empty so stale files cannot enter the Dataset"
        )
    args.output.mkdir(parents=True, exist_ok=True)

    copies = {
        args.package / "annotations.jsonl": Path("data/superset/blinded_pool.jsonl"),
        args.package / "sources.jsonl": Path("data/superset/sources.jsonl"),
        args.package / "dataset_info.json": Path("dataset_info.json"),
        args.package / "package_manifest.json": Path(
            "metadata/bakeoff_pool_manifest.json"
        ),
        args.package / "provenance.jsonl": Path("private/system_provenance.jsonl"),
        args.tranche / "first_pass.jsonl": Path("data/first_pass/blinded_pool.jsonl"),
        args.tranche / "first_pass_manifest.json": Path(
            "data/first_pass/manifest.json"
        ),
        args.tranche / "first_pass_provenance.jsonl": Path(
            "private/first_pass_system_provenance.jsonl"
        ),
        args.tranche / "silver_diagnostics.jsonl": Path(
            "diagnostics/silver_diagnostics.jsonl"
        ),
        args.snapshot_manifest: Path("metadata/source_snapshot_manifest.json"),
        Path("docs/embedding-bakeoff-20260718.md"): Path("metadata/bakeoff_report.md"),
        Path("backend/config/embedding_bakeoff.json"): Path(
            "metadata/embedding_bakeoff.json"
        ),
        Path("backend/scripts/related_papers_annotation.py"): Path(
            "workflow/related_papers_annotation.py"
        ),
        Path("backend/scripts/score_related_papers_annotations.py"): Path(
            "workflow/score_related_papers_annotations.py"
        ),
        Path("backend/services/embedding_annotation.py"): Path(
            "workflow/embedding_annotation.py"
        ),
    }
    for source, relative in copies.items():
        copy(source, args.output / relative)
    for run in sorted((args.package / "runs").glob("*.json")):
        copy(run, args.output / "private" / "runs" / run.name)

    readme = """---
pretty_name: Papers With Code Related-Paper Relevance Judgments
license: other
task_categories:
- text-retrieval
language:
- en
---

# Papers With Code related-paper relevance judgments

Private canonical collection package for blinded human evaluation of related-paper and hybrid-search retrieval. This revision contains **no real human judgments**. It preserves the verified 100-source, 1,400-pair superset and a balanced 40-source, 240-pair first-pass tranche.

## Annotation question and rubric

Would the candidate be a useful next paper for someone researching the source paper's central technical contribution?

- `2`: strongly related — shared central problem/method, direct extension, substantial adoption, comparison, or evaluation.
- `1`: somewhat related — useful central topical or technical connection, but a materially different main question.
- `0`: unrelated — superficial terminology, broad category, author/venue overlap, or no meaningful research connection.
- `unsure` and `skip` persist without a grade and must be resolved or reported separately.

Annotators must use only `data/first_pass/blinded_pool.jsonl`; keep `private/` hidden until labels and adjudication are frozen. The synthetic trap items produced by the workflow are attention checks and are not judgments on real papers.

## Local workflow

From the Papers With Code checkout:

```bash
uv run --env-file backend/keys.env python backend/scripts/related_papers_annotation.py serve \\
  --tranche /PATH/TO/data/first_pass/blinded_pool.jsonl \\
  --state-dir /PATH/TO/annotation-state --annotator-id ANNOTATOR_1 \\
  --annotator-index 0 --annotator-count 2 --open-browser
```

Run `verify-package --root /PATH/TO/DATASET` before annotation. Progress is atomically saved per annotator and bound to an assignment checksum. Use the script's `export`, `merge`, `serve-adjudication`, `export-adjudication`, and `validate` commands for the complete workflow. Scoring requires the explicit `--confirm UNBLIND_AND_SCORE` gate and must happen only after judgments are frozen.

## First-pass design and expansion

The first pass has 20 sources, four from each document-length quintile, and retains every de-duplicated pooled candidate for those sources. This keeps all 13 systems' top four fully judgeable while reducing the source set. With two annotators, 20% cross-annotator overlap, 5% hidden repeats, and 2% synthetic traps, the exact assignment counts are recorded in the manifest. At 35–45 seconds per item, budget roughly two hours per annotator.

Expand in balanced 20-source batches when weighted agreement is below 0.65, unsure/skip exceeds 10%, a leading pairwise 95% bootstrap interval includes zero, a leading nDCG@4 interval is wider than 0.08, or any system has under 90% judged top-4 coverage. The preserved 1,400-pair superset is the ceiling for this phase.

## Quality control and interpretation

QC combines hidden exact repeats (intra-annotator consistency), 20% shared assignments (inter-annotator agreement), and a small number of obviously cross-domain synthetic traps. Trap expectations never create labels for real papers. Report trap accuracy, repeat agreement, unsure/skip rate, adjudication rate, and per-system coverage.

Task overlap, lexical overlap, possible duplicates/versions, citation, and lineage signals are weak/silver diagnostics only. Missing task/lineage/citation values mean those signals were unavailable in the immutable snapshot. They cannot replace human judgments or select a production model.

## Provenance, privacy, and license

The ordered 5,000-paper snapshot is the immutable `pilot-20260718` export in private Bucket `nielsr/pwc-paper-embeddings`; its manifest and bakeoff report are included under `metadata/`. System mappings and runs are under `private/`. Paper titles and abstracts originate from research metadata and may retain upstream copyright; this private package is for internal research evaluation, not relicensing or public redistribution. Annotator IDs must be pseudonymous and notes must not include personal or secret information. Raw production search queries are absent.
"""
    (args.output / "README.md").write_text(readme, encoding="utf-8")
    (args.output / "LICENSE_AND_PRIVACY.md").write_text(
        """# License and privacy notes\n\nThe workflow code follows the repository license. Paper titles and abstracts retain their upstream rights and are included only in this private internal evaluation package; no new license is asserted over them. Do not publish this Dataset without a separate rights and privacy review.\n\nUse pseudonymous annotator IDs. Do not enter names, email addresses, credentials, unpublished review content, production queries, or other personal/sensitive data in notes. System provenance is private until judgments are frozen.\n""",
        encoding="utf-8",
    )
    provenance = {
        "schema_version": "pwc-related-dataset-provenance-v1",
        "created_utc": "2026-07-18",
        "bucket": "nielsr/pwc-paper-embeddings",
        "snapshot_run": "pilot-20260718",
        "snapshot_prefix": "runs/pilot-f2llm-5000-20260718T125302Z/input",
        "snapshot_rows": 5000,
        "bakeoff_job_ids": [
            "6a5b7987d216bd6f3a1fe5df",
            "6a5b7e92d216bd6f3a1fe660",
            "6a5b7f46bee6ee1cf4ecf606",
            "6a5b7ff2d216bd6f3a1fe688",
        ],
        "package": package_summary,
        "human_judgments_present": False,
    }
    (args.output / "metadata" / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    checksums = [
        f"{sha256_file(path)}  {path.relative_to(args.output)}" for path in files
    ]
    (args.output / "checksums.sha256").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "pwc-related-dataset-package-v1",
        "file_count": len(files) + 2,
        "superset": package_summary,
        "first_pass": json.loads(
            (args.tranche / "first_pass_manifest.json").read_text(encoding="utf-8")
        ),
        "checksums_sha256": sha256_file(args.output / "checksums.sha256"),
    }
    (args.output / "package_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
