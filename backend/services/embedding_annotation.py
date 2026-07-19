"""Deterministic tooling for blinded related-paper human annotation."""

from __future__ import annotations

import hashlib
import json
import random
import re
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "pwc-related-annotation-v2"
VALID_GRADES = {0, 1, 2}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksum_manifest(root: Path) -> dict[str, Any]:
    manifest = root / "checksums.sha256"
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = (root / relative).resolve()
        if root.resolve() not in target.parents:
            raise ValueError(f"Checksum path escapes package root: {relative}")
        if sha256_file(target) != expected:
            raise ValueError(f"Checksum mismatch: {relative}")
        checked += 1
    return {"verified_files": checked, "checksums_sha256": sha256_file(manifest)}


def stable_fraction(value: str, seed: int) -> float:
    raw = hashlib.sha256(f"{seed}:{value}".encode()).digest()[:8]
    return int.from_bytes(raw) / (2**64 - 1)


def assignment_sha256(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(row["item_id"] for row in rows).encode()
    ).hexdigest()


def validate_package(package: Path) -> dict[str, Any]:
    annotations = read_jsonl(package / "annotations.jsonl")
    provenance = read_jsonl(package / "provenance.jsonl")
    sources = read_jsonl(package / "sources.jsonl")
    manifest = json.loads(
        (package / "package_manifest.json").read_text(encoding="utf-8")
    )
    ids = [row["blind_id"] for row in annotations]
    pairs = [(row["source_paper_id"], row["candidate_paper_id"]) for row in annotations]
    if len(ids) != len(set(ids)) or len(pairs) != len(set(pairs)):
        raise ValueError(
            "Annotation blind IDs and source-candidate pairs must be unique"
        )
    if any(source == candidate for source, candidate in pairs):
        raise ValueError("The source paper cannot be its own candidate")
    provenance_ids = [row["blind_id"] for row in provenance]
    if set(ids) != set(provenance_ids) or len(provenance_ids) != len(
        set(provenance_ids)
    ):
        raise ValueError("Provenance coverage does not exactly match annotations")
    if manifest["pair_count"] != len(annotations) or manifest["source_count"] != len(
        sources
    ):
        raise ValueError("Package manifest counts do not match package data")
    if any(row.get("grade") is not None for row in annotations):
        raise ValueError("Canonical annotation pool must not contain human labels")
    return {
        "source_count": len(sources),
        "pair_count": len(annotations),
        "system_count": len(manifest["systems"]),
        "annotation_sha256": sha256_file(package / "annotations.jsonl"),
        "provenance_sha256": sha256_file(package / "provenance.jsonl"),
    }


def build_first_pass(
    package: Path,
    output: Path,
    *,
    source_count: int = 20,
    pairs_per_source: int = 0,
    seed: int = 20260718,
) -> dict[str, Any]:
    """Select a balanced coverage-first tranche without creating judgments."""
    validate_package(package)
    annotations = read_jsonl(package / "annotations.jsonl")
    sources = read_jsonl(package / "sources.jsonl")
    provenance = {
        row["blind_id"]: row["systems"]
        for row in read_jsonl(package / "provenance.jsonl")
    }
    systems = sorted(
        {item["system"] for values in provenance.values() for item in values}
    )
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        by_stratum[source["stratum"]].append(source)
    selected_sources: list[int] = []
    strata = sorted(by_stratum)
    for index, stratum in enumerate(strata):
        target = source_count // len(strata) + (index < source_count % len(strata))
        ranked_sources = sorted(
            by_stratum[stratum],
            key=lambda row: stable_fraction(str(row["source_paper_id"]), seed),
        )
        selected_sources.extend(
            int(row["source_paper_id"]) for row in ranked_sources[:target]
        )

    by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in annotations:
        if row["source_paper_id"] in selected_sources:
            by_source[int(row["source_paper_id"])].append(row)

    selected: list[dict[str, Any]] = []
    global_counts = defaultdict(int)
    for source in sorted(selected_sources):
        available = list(by_source[source])
        chosen: list[dict[str, Any]] = []
        target_pairs = len(available) if pairs_per_source <= 0 else pairs_per_source
        while available and len(chosen) < target_pairs:

            def priority(row: dict[str, Any]) -> tuple[float, float, str]:
                evidence = provenance[row["blind_id"]]
                coverage = sum(
                    1 / (1 + global_counts[item["system"]]) for item in evidence
                )
                rank_signal = sum(1 / item["rank"] for item in evidence)
                exclusivity = 1 / len(evidence)
                return (
                    coverage + rank_signal * 0.15 + exclusivity * 0.25,
                    stable_fraction(row["blind_id"], seed),
                    row["blind_id"],
                )

            pick = max(available, key=priority)
            available.remove(pick)
            chosen.append(pick)
            for item in provenance[pick["blind_id"]]:
                global_counts[item["system"]] += 1
        selected.extend(chosen)

    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "first_pass.jsonl", selected)
    selected_ids = {row["blind_id"] for row in selected}
    write_jsonl(
        output / "first_pass_provenance.jsonl",
        (
            {"blind_id": blind_id, "systems": provenance[blind_id]}
            for blind_id in sorted(selected_ids)
        ),
    )
    counts = {system: global_counts[system] for system in systems}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "source_count": len(selected_sources),
        "pair_count": len(selected),
        "pairs_per_source": "all pooled candidates"
        if pairs_per_source <= 0
        else pairs_per_source,
        "source_strata": {
            stratum: sum(
                1
                for source in selected_sources
                if any(
                    item["source_paper_id"] == source and item["stratum"] == stratum
                    for item in sources
                )
            )
            for stratum in strata
        },
        "system_pair_coverage": counts,
        "superset_pair_count": len(annotations),
        "selection": "balanced source strata; all de-duplicated pooled candidates retained for complete per-system top-4 judgments",
        "expansion_rule": {
            "batch_sources": 20,
            "conditions": [
                "weighted agreement below 0.65",
                "unsure or skip rate above 0.10",
                "any leading pairwise 95% bootstrap CI includes zero",
                "any leading system nDCG@4 95% CI width exceeds 0.08",
                "any system top-4 judgment coverage is below 0.90",
            ],
            "maximum": "retain and expand through the original 100-source/1,400-pair superset",
        },
    }
    manifest["recommended_two_annotator_assignment"] = {
        f"annotator-{index + 1}": len(
            build_assignment(selected, f"annotator-{index + 1}", index, 2, seed=seed)
        )
        for index in range(2)
    }
    (output / "first_pass_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def trap_items() -> list[dict[str, Any]]:
    """Synthetic attention checks; these are not labels for real paper pairs."""
    return [
        {
            "blind_id": "qc-trap-astronomy-cooking",
            "source_paper_id": -1,
            "source_title": "Calibrating Spectrographs for Exoplanet Transit Astronomy",
            "source_abstract": "A synthetic astronomy abstract about telescope calibration and exoplanet transits.",
            "candidate_paper_id": -2,
            "candidate_title": "Optimizing Sourdough Fermentation in Home Ovens",
            "candidate_abstract": "A synthetic cooking abstract about flour hydration and bread fermentation.",
            "source_stratum": "synthetic_qc",
            "display_order": 0,
            "grade": None,
            "notes": None,
            "expected_grade": 0,
        },
        {
            "blind_id": "qc-trap-robotics-poetry",
            "source_paper_id": -3,
            "source_title": "Force-Controlled Robotic Grasp Planning",
            "source_abstract": "A synthetic robotics abstract about grasp stability and force control.",
            "candidate_paper_id": -4,
            "candidate_title": "Meter and Rhyme in Seventeenth-Century Poetry",
            "candidate_abstract": "A synthetic literary-studies abstract about poetic meter and rhyme.",
            "source_stratum": "synthetic_qc",
            "display_order": 0,
            "grade": None,
            "notes": None,
            "expected_grade": 0,
        },
    ]


def build_assignment(
    rows: list[dict[str, Any]],
    annotator_id: str,
    annotator_index: int,
    annotator_count: int,
    *,
    overlap: float = 0.20,
    duplicate_rate: float = 0.05,
    trap_rate: float = 0.02,
    seed: int = 20260718,
) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", annotator_id):
        raise ValueError(
            "Annotator ID may contain only letters, digits, dot, underscore, and dash"
        )
    if not 0 <= annotator_index < annotator_count:
        raise ValueError("Annotator index must be in [0, annotator_count)")
    assignment = []
    for row in rows:
        bucket = (
            int(hashlib.sha256(row["blind_id"].encode()).hexdigest(), 16)
            % annotator_count
        )
        shared = stable_fraction("overlap:" + row["blind_id"], seed) < overlap
        if bucket == annotator_index or shared:
            item = dict(row)
            item.update(
                {
                    "item_id": row["blind_id"],
                    "base_blind_id": row["blind_id"],
                    "item_type": "real",
                }
            )
            assignment.append(item)
    duplicate_count = (
        max(1, round(len(assignment) * duplicate_rate)) if assignment else 0
    )
    duplicate_pool = sorted(
        assignment, key=lambda row: stable_fraction("duplicate:" + row["item_id"], seed)
    )
    for number, original in enumerate(duplicate_pool[:duplicate_count], 1):
        duplicate = dict(original)
        duplicate.update(
            {
                "item_id": f"qc-duplicate-{number:03d}-{original['base_blind_id']}",
                "item_type": "duplicate",
            }
        )
        assignment.append(duplicate)
    desired_traps = max(1, round(len(assignment) * trap_rate)) if assignment else 0
    traps = trap_items()
    for number in range(desired_traps):
        trap = dict(traps[number % len(traps)])
        trap.update(
            {
                "item_id": f"{trap['blind_id']}-{number + 1}",
                "base_blind_id": trap["blind_id"],
                "item_type": "trap",
            }
        )
        assignment.append(trap)
    random.Random(f"{seed}:{annotator_id}").shuffle(assignment)
    return assignment


def validate_label(label: dict[str, Any]) -> None:
    status = label.get("status")
    grade = label.get("grade")
    if status not in {"graded", "unsure", "skipped"}:
        raise ValueError("Annotation status must be graded, unsure, or skipped")
    if status == "graded" and grade not in VALID_GRADES:
        raise ValueError("Graded annotations require grade 0, 1, or 2")
    if status != "graded" and grade is not None:
        raise ValueError("Unsure and skipped annotations must not carry a grade")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def export_annotations(
    assignment: list[dict[str, Any]], state: dict[str, Any], output: Path
) -> dict[str, Any]:
    by_id = {row["item_id"]: row for row in assignment}
    if state.get("assignment_sha256") != assignment_sha256(assignment):
        raise ValueError("Saved state belongs to a different assignment")
    labels = state.get("labels", {})
    rows = []
    for item_id, label in sorted(labels.items()):
        if item_id not in by_id:
            raise ValueError(f"State contains an unknown item: {item_id}")
        validate_label(label)
        item = by_id[item_id]
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "annotator_id": state["annotator_id"],
                "item_id": item_id,
                "base_blind_id": item["base_blind_id"],
                "item_type": item["item_type"],
                "grade": label.get("grade"),
                "status": label["status"],
                "notes": label.get("notes") or None,
                "updated_at": label.get("updated_at"),
                "expected_grade": item.get("expected_grade"),
            }
        )
    write_jsonl(output, rows)
    summary = {
        "annotator_id": state["annotator_id"],
        "assigned": len(assignment),
        "exported": len(rows),
        "graded": sum(row["status"] == "graded" for row in rows),
        "unsure": sum(row["status"] == "unsure" for row in rows),
        "skipped": sum(row["status"] == "skipped" for row in rows),
        "sha256": sha256_file(output),
    }
    return summary


def merge_exports(paths: list[Path], output: Path) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for path in paths:
        for row in read_jsonl(path):
            key = (row["annotator_id"], row["item_id"])
            if key in seen:
                raise ValueError(f"Duplicate annotator item: {key}")
            seen.add(key)
            validate_label(row)
            if row["item_type"] == "real":
                grouped[row["base_blind_id"]].append(row)
    merged = []
    for blind_id, values in sorted(grouped.items()):
        grades = [row["grade"] for row in values if row["status"] == "graded"]
        consensus = grades[0] if grades and len(set(grades)) == 1 else None
        merged.append(
            {
                "schema_version": SCHEMA_VERSION,
                "blind_id": blind_id,
                "annotations": values,
                "consensus_grade": consensus,
                "final_grade": consensus,
                "needs_adjudication": len(grades) > 1 and len(set(grades)) > 1,
                "adjudication_notes": None,
            }
        )
    write_jsonl(output, merged)
    disagreements = sum(row["needs_adjudication"] for row in merged)
    return {
        "pairs": len(merged),
        "disagreements": disagreements,
        "sha256": sha256_file(output),
    }


def validate_adjudicated(path: Path) -> dict[str, Any]:
    rows = read_jsonl(path)
    ids = [row["blind_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Adjudicated blind IDs must be unique")
    for row in rows:
        grade = row.get("final_grade")
        if grade is not None and grade not in VALID_GRADES:
            raise ValueError("Final grades must be 0, 1, 2, or null")
        if row.get("needs_adjudication") and grade is None:
            raise ValueError(f"Unresolved disagreement: {row['blind_id']}")
    return {
        "pairs": len(rows),
        "judged": sum(row.get("final_grade") in VALID_GRADES for row in rows),
        "sha256": sha256_file(path),
    }


def silver_diagnostics(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    token_pattern = re.compile(r"[a-z0-9]+")
    diagnostics = []
    for row in annotations:
        source_title = " ".join(token_pattern.findall(row["source_title"].lower()))
        candidate_title = " ".join(
            token_pattern.findall(row["candidate_title"].lower())
        )
        source_tokens = set(
            token_pattern.findall(
                (row["source_title"] + " " + row["source_abstract"]).lower()
            )
        )
        candidate_tokens = set(
            token_pattern.findall(
                (row["candidate_title"] + " " + row["candidate_abstract"]).lower()
            )
        )
        union = source_tokens | candidate_tokens
        diagnostics.append(
            {
                "blind_id": row["blind_id"],
                "lexical_jaccard": len(source_tokens & candidate_tokens) / len(union)
                if union
                else 0.0,
                "normalized_title_exact": source_title == candidate_title,
                "normalized_title_token_jaccard": len(
                    set(source_title.split()) & set(candidate_title.split())
                )
                / max(1, len(set(source_title.split()) | set(candidate_title.split()))),
                "possible_version_or_duplicate": source_title == candidate_title
                or (len(source_title.split()) >= 4 and candidate_title in source_title),
                "task_overlap": None,
                "explicit_lineage_edge": None,
                "explicit_citation_edge": None,
                "limitations": "weak/silver only; task, lineage, and citation edges are unavailable in the immutable snapshot",
            }
        )
    return diagnostics


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def weighted_agreement(exports: list[dict[str, Any]]) -> float | None:
    by_pair: dict[str, list[int]] = defaultdict(list)
    for row in exports:
        if row["item_type"] == "real" and row["status"] == "graded":
            by_pair[row["base_blind_id"]].append(row["grade"])
    scores = [
        1 - abs(values[0] - values[1]) / 2
        for values in by_pair.values()
        if len(values) >= 2
    ]
    return statistics.mean(scores) if scores else None


def qc_summary(exports: list[dict[str, Any]]) -> dict[str, Any]:
    by_annotator_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    trap_results = []
    for row in exports:
        if row["status"] == "graded" and row["item_type"] in {"real", "duplicate"}:
            by_annotator_pair[(row["annotator_id"], row["base_blind_id"])].append(
                row["grade"]
            )
        if row["status"] == "graded" and row["item_type"] == "trap":
            trap_results.append(row["grade"] == row.get("expected_grade"))
    repeats = [grades for grades in by_annotator_pair.values() if len(grades) > 1]
    return {
        "assignments": len(exports),
        "unsure_rate": sum(row["status"] == "unsure" for row in exports)
        / max(1, len(exports)),
        "skip_rate": sum(row["status"] == "skipped" for row in exports)
        / max(1, len(exports)),
        "hidden_repeat_count": len(repeats),
        "hidden_repeat_exact_agreement": sum(
            len(set(grades)) == 1 for grades in repeats
        )
        / max(1, len(repeats)),
        "synthetic_trap_count": len(trap_results),
        "synthetic_trap_accuracy": sum(trap_results) / max(1, len(trap_results)),
        "cross_annotator_weighted_agreement": weighted_agreement(exports),
    }
