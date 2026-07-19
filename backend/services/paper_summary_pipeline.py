"""Deterministic contracts for immutable title-and-abstract paper summaries."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.models.database import Paper
from backend.services.embedding_contracts import normalize_embedding_text, sha256_file


INPUT_FORMAT_VERSION = "paper-summary-title-abstract-v1"
PROMPT_VERSION = "retrieval-summary-v10-source-aware"
MANIFEST_SCHEMA_VERSION = "paper-summaries-v1"
MIN_SUMMARY_WORDS = 80
MIN_SHORT_SOURCE_SUMMARY_WORDS = 30
MAX_SUMMARY_WORDS = 120
SHORT_SOURCE_ABSTRACT_WORDS = 100
GENERATION_PARAMETERS = {
    "temperature": 0.0,
    "top_p": 1.0,
    "top_k": -1,
    "max_tokens": 192,
    "seed": 0,
    "thinking": False,
    "max_validation_attempts": 5,
}

SYSTEM_PROMPT = """You write factual retrieval summaries of research papers.
Use only the supplied title and abstract. Do not add outside knowledge, citations,
unsupported claims, or generic commentary. Return only the summary text."""

USER_PROMPT_TEMPLATE = """Write one concise {minimum_words}–120 word retrieval-oriented summary; aim for {target_words} words.
Preserve the paper's central problem, primary method or contribution, experimental
or deployment setting, and principal result when each is stated. Do not invent a
missing result. Use concrete technical terms that would help retrieve this paper.
Do not include a heading, citation, bullet list, or boilerplate such as \"this paper
presents\".

Title: {title}

Abstract: {abstract}"""

REPAIR_PROMPT_TEMPLATE = """Rewrite the draft as one factual 100–110 word summary.
It had {word_count} words and failed these checks: {validation_errors}.
Count the words before responding. Return only the corrected summary as one
paragraph. Retain only claims supported by the title and abstract. Do not output
the word count, analysis, self-correction, or a second draft.

Title: {title}

Abstract: {abstract}

Draft: {draft}"""

SHORT_REPAIR_PROMPT_TEMPLATE = """Rewrite the draft as exactly six complete sentences of 14–16 words each.
Use only the title and abstract. Map the sentences to the contribution,
participants, setting, collection method, annotation, and scope when applicable.
Redistribute or rephrase source details if a category is absent; never add a new
claim. Do not claim benefits, challenges, comparisons, exclusions, or intended
uses unless explicitly stated. Return one paragraph only; do not output a word
count, analysis, or self-correction.

Title: {title}

Abstract: {abstract}

Draft: {draft}"""

PROMPT_HASH = hashlib.sha256(
    (
        f"{PROMPT_VERSION}\0{SYSTEM_PROMPT}\0{USER_PROMPT_TEMPLATE}"
        f"\0{REPAIR_PROMPT_TEMPLATE}\0{SHORT_REPAIR_PROMPT_TEMPLATE}"
    ).encode("utf-8")
).hexdigest()

_WORD = re.compile(r"\b[\w]+(?:[-'][\w]+)*\b", re.UNICODE)
_BOILERPLATE = (
    "here is the summary",
    "here's the summary",
    "this paper presents",
    "the provided abstract",
    "as an ai language model",
    "i cannot",
)
_CITATION = re.compile(r"\[[0-9]+(?:\s*[-,]\s*[0-9]+)*\]")
_MODEL_META_MARKERS = (
    "\n\n*Self-Correction",
    "\n\n(Self-correction",
    "\n\nWord count:",
    "\nWord count:",
)


def build_summary_input(title: str, abstract: str | None) -> tuple[str, str]:
    """Return normalized title and abstract without adding any other metadata."""
    return normalize_embedding_text(title), normalize_embedding_text(abstract)


def summary_input_hash(title: str, abstract: str | None) -> str:
    normalized_title, normalized_abstract = build_summary_input(title, abstract)
    payload = f"{INPUT_FORMAT_VERSION}\0{normalized_title}\0{normalized_abstract}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_word_bounds(abstract: str | None = None) -> tuple[int, int]:
    """Scale the lower bound for terse sources so validation does not reward padding."""
    if abstract is None:
        return MIN_SUMMARY_WORDS, MAX_SUMMARY_WORDS
    source_words = count_words(normalize_embedding_text(abstract))
    if source_words >= SHORT_SOURCE_ABSTRACT_WORDS:
        return MIN_SUMMARY_WORDS, MAX_SUMMARY_WORDS
    minimum = min(
        MIN_SUMMARY_WORDS,
        max(MIN_SHORT_SOURCE_SUMMARY_WORDS, math.ceil(0.75 * source_words)),
    )
    return minimum, MAX_SUMMARY_WORDS


def render_messages(title: str, abstract: str) -> list[dict[str, str]]:
    minimum_words, maximum_words = summary_word_bounds(abstract)
    target_words = (
        "100–110"
        if minimum_words == MIN_SUMMARY_WORDS
        else f"{minimum_words}–{min(maximum_words, minimum_words + 20)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                minimum_words=minimum_words,
                target_words=target_words,
                title=title,
                abstract=abstract,
            ),
        },
    ]


def count_words(value: str) -> int:
    return len(_WORD.findall(value))


def validate_summary(value: str, *, abstract: str | None = None) -> list[str]:
    errors: list[str] = []
    summary = value.strip()
    if not summary:
        return ["empty"]
    try:
        summary.encode("utf-8", errors="strict")
    except UnicodeError:
        errors.append("invalid_utf8")
    words = count_words(summary)
    minimum_words, maximum_words = summary_word_bounds(abstract)
    if words < minimum_words:
        errors.append("too_short")
    if words > maximum_words:
        errors.append("too_long")
    lowered = summary.casefold()
    if any(phrase in lowered for phrase in _BOILERPLATE):
        errors.append("boilerplate")
    if "<think" in lowered or "</think" in lowered:
        errors.append("thinking_markup")
    if _CITATION.search(summary):
        errors.append("citation_like")
    if any(ord(character) < 32 and character not in "\n\t" for character in summary):
        errors.append("control_character")
    return errors


def strip_model_meta_postamble(value: str) -> str:
    """Remove an explicitly marked word-count/self-correction postamble."""
    summary = value.strip()
    positions = [summary.find(marker) for marker in _MODEL_META_MARKERS]
    positions = [position for position in positions if position >= 0]
    if positions:
        summary = summary[: min(positions)].strip()
    summary = re.sub(r"\s*\(\s*\d+\s+words?\s*\)\s*$", "", summary, flags=re.IGNORECASE)
    return summary.strip()


@dataclass(frozen=True)
class SummaryExportResult:
    input_dir: Path
    manifest: dict[str, object]


def configure_summary_snapshot(db: Session) -> None:
    """Start the read-only repeatable-read transaction before any snapshot query."""
    if db.in_transaction():
        raise ValueError("Summary snapshot transaction must be configured first")
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))


def _ids_hash(ids: Iterable[int]) -> str:
    payload = "\n".join(str(value) for value in ids) + "\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def choose_representative_ids(
    candidates: list[dict[str, object]],
    *,
    forced_ids: list[int],
    size: int,
    external_target: int = 15,
) -> list[int]:
    """Choose deterministic source/category/era/length-stratified paper IDs."""
    if size < len(set(forced_ids)):
        raise ValueError("Representative size is smaller than the forced set")
    by_id = {int(row["id"]): row for row in candidates}
    missing = sorted(set(forced_ids) - set(by_id))
    if missing:
        raise ValueError(f"Forced papers are absent or ineligible: {missing}")

    def era(row: dict[str, object]) -> str:
        published = row.get("date_published")
        year = published.year if published else 0
        if year < 2018:
            return "pre2018"
        if year < 2023:
            return "2018-2022"
        if year < 2025:
            return "2023-2024"
        return "2025+"

    def length_band(row: dict[str, object]) -> str:
        length = int(row.get("abstract_chars") or 0)
        return "short" if length < 700 else "medium" if length < 1_400 else "long"

    def category(row: dict[str, object]) -> str:
        value = str(row.get("primary_category") or "other")
        if value in {"cs.CV", "cs.CL", "cs.RO", "cs.AI"}:
            return value
        if value in {"cs.LG", "stat.ML"}:
            return "ml"
        if value.startswith("q-bio"):
            return "q-bio"
        return "other"

    forced = sorted(set(forced_ids))
    forced_external = sum(
        by_id[paper_id]["source"] == "external" for paper_id in forced
    )
    external_target = min(size, max(forced_external, external_target))
    source_targets = {"external": external_target, "arxiv": size - external_target}
    selected = set(forced)

    for source, target in source_targets.items():
        current = sum(by_id[paper_id]["source"] == source for paper_id in selected)
        needed = target - current
        strata: dict[tuple[str, str, str], list[int]] = {}
        for row in candidates:
            paper_id = int(row["id"])
            if row["source"] != source or paper_id in selected:
                continue
            key = (category(row), era(row), length_band(row))
            strata.setdefault(key, []).append(paper_id)
        for key, values in strata.items():
            values.sort(
                key=lambda paper_id: hashlib.sha256(
                    f"paper-summary-representative-v1\0{key}\0{paper_id}".encode()
                ).hexdigest()
            )
        keys = sorted(strata)
        while needed:
            progressed = False
            for key in keys:
                if needed == 0:
                    break
                values = strata[key]
                if values:
                    selected.add(values.pop(0))
                    needed -= 1
                    progressed = True
            if not progressed:
                raise ValueError(
                    f"Not enough eligible {source} papers for target {target}"
                )
    result = sorted(selected)
    if len(result) != size:
        raise ValueError(f"Representative selection produced {len(result)} != {size}")
    return result


def select_representative_paper_ids(
    db: Session,
    *,
    forced_ids: list[int],
    size: int,
) -> list[int]:
    rows = (
        db.query(
            Paper.id,
            Paper.source,
            Paper.primary_category,
            Paper.date_published,
            func.length(Paper.abstract).label("abstract_chars"),
        )
        .filter(
            Paper.is_latest_version,
            func.length(func.btrim(Paper.title)) > 0,
            func.length(func.btrim(Paper.abstract)) > 0,
        )
        .all()
    )
    candidates = [dict(row._mapping) for row in rows]
    return choose_representative_ids(candidates, forced_ids=forced_ids, size=size)


def export_summary_snapshot(
    db: Session,
    output_root: Path,
    *,
    run_id: str,
    shard_rows: int = 2_000,
    paper_ids: list[int] | None = None,
    snapshot_configured: bool = False,
) -> SummaryExportResult:
    """Export one ordered repeatable-read snapshot without mutating the database."""
    if shard_rows < 1:
        raise ValueError("shard_rows must be positive")
    input_dir = output_root / "summary-generation" / run_id / "input"
    if input_dir.exists() and any(input_dir.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty run directory: {input_dir}")
    input_dir.mkdir(parents=True, exist_ok=True)

    if not snapshot_configured:
        configure_summary_snapshot(db)
    corpus_snapshot = str(
        db.execute(text("SELECT txid_current_snapshot()::text")).scalar_one()
    )
    snapshot_time = db.execute(text("SELECT transaction_timestamp()")).scalar_one()
    latest_count = (
        db.query(func.count(Paper.id)).filter(Paper.is_latest_version).scalar()
    )
    eligible_query = db.query(Paper).filter(
        Paper.is_latest_version,
        func.length(func.btrim(Paper.title)) > 0,
        func.length(func.btrim(Paper.abstract)) > 0,
    )
    eligible_count = eligible_query.count()
    if paper_ids is not None:
        requested = sorted(set(paper_ids))
        eligible_query = eligible_query.filter(Paper.id.in_(requested))
    else:
        requested = None
    papers = eligible_query.order_by(Paper.id).all()
    if requested is not None:
        found = [paper.id for paper in papers]
        missing = sorted(set(requested) - set(found))
        if missing:
            raise ValueError(f"Requested papers are absent or ineligible: {missing}")

    shards: list[dict[str, object]] = []
    ordered_ids: list[int] = []
    for shard_index, start in enumerate(range(0, len(papers), shard_rows)):
        shard_papers = papers[start : start + shard_rows]
        path = input_dir / f"papers-{shard_index:05d}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for paper in shard_papers:
                title, abstract = build_summary_input(paper.title, paper.abstract)
                record = {
                    "paper_id": paper.id,
                    "arxiv_id": paper.arxiv_id,
                    "paper_identifier": paper.arxiv_id or f"external:{paper.id}",
                    "title": title,
                    "abstract": abstract,
                    "input_hash": summary_input_hash(title, abstract),
                }
                handle.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                ordered_ids.append(paper.id)
        shards.append(
            {"path": path.name, "rows": len(shard_papers), "sha256": sha256_file(path)}
        )

    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_format_version": INPUT_FORMAT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH,
        "generation_parameters": GENERATION_PARAMETERS,
        "corpus_snapshot": corpus_snapshot,
        "snapshot_time": snapshot_time.isoformat(),
        "latest_paper_count": latest_count,
        "eligible_paper_count": eligible_count,
        "excluded_missing_title_or_abstract": latest_count - eligible_count,
        "row_count": len(papers),
        "ordered_paper_ids_sha256": _ids_hash(ordered_ids),
        "shards": shards,
    }
    (input_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return SummaryExportResult(input_dir=input_dir, manifest=manifest)
