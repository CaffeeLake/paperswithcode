"""
Preview MTEB leaderboard evaluations as CSV manifests for review.

This is a READ-ONLY preview step: it does NOT write to the database. It
loads MTEB benchmark results from the official `mteb/results` source via
the `mteb` Python package, computes the official aggregate plus per
task-type rollups for the three benchmarks we want to feature on
`embedding-models` (English, Multilingual, Code), resolves a candidate
paper for each model, and emits three CSV manifests for human review:

- `mteb_papers.csv`: one row per model, with the resolution decision
  (existing arxiv paper, missing arxiv that we'd need to import,
  existing external row, new external row, or skipped).
- `mteb_evaluations.csv`: one row per (model, benchmark, metric) plus
  per-task-type rollups, with model metadata that would be persisted on
  the `evaluations` row in a follow-up step.
- `mteb_skipped.csv`: rows we would not import (no paper, ambiguous
  release date, incomplete benchmark coverage, etc.).

Usage:

    # First clone the official results repo if not already present:
    #   git clone --depth 1 https://github.com/embeddings-benchmark/results.git \
    #       /root/.cache/mteb_data/results
    uv run --env-file backend/keys.env --with mteb \
        python backend/database/evaluations_setup/preview_mteb_evaluations.py

The script does NOT alter the database. After review, the importer step
in the plan can reuse the same logic to materialise the rows.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("preview_mteb")
logger.setLevel(logging.INFO)
# mteb prints a lot of warnings about old result files; silence them so the
# preview output is readable.
logging.getLogger("mteb").setLevel(logging.ERROR)

import mteb  # noqa: E402  (after warning suppression)
from mteb.cache import ResultCache  # noqa: E402

from backend.database.connection import db_manager  # noqa: E402
from backend.models.database import Paper as DBPaper  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Where the mteb/results repo is checked out. Override via env var.
DEFAULT_CACHE_PATH = Path(
    os.environ.get("MTEB_RESULTS_PATH", "/root/.cache/mteb_data/results")
)

# Output directory for CSV manifests, kept under the importer folder so
# it is easy to discover next to the future importer.
PREVIEW_DIR = Path(__file__).parent / "_mteb_preview"

# Which benchmarks we feature, mapped to the dataset name we will use on
# the embedding-models task page. The aggregate metric stored on the
# evaluation row uses "MTEB Score" (0–100, higher is better) for the
# top-level aggregate and per-task-type rollups alike.
FEATURED_BENCHMARKS: list[tuple[str, str]] = [
    ("MTEB(eng, v2)", "MTEB"),
    ("MTEB(Multilingual, v2)", "MTEB Multilingual"),
    ("MTEB(Code, v1)", "MTEB Code"),
]

# Mapping from MTEB task-type strings to the embedding-models subtask
# slugs we will create / reuse. Anything not in this map will be reported
# but skipped from the preview to keep scope tight for the first pass.
TASK_TYPE_TO_SUBTASK_SLUG: dict[str, str] = {
    "Retrieval": "retrieval",
    "Classification": "classification",
    "Clustering": "clustering",
    "STS": "semantic-textual-similarity",
    "PairClassification": "pair-classification",
    "Reranking": "reranking",
    "Summarization": "summarization",
    "BitextMining": "bitext-mining",
    "InstructionReranking": "instruction-retrieval",
    "MultilabelClassification": "multilabel-classification",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")
ARXIV_URL_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", re.IGNORECASE)


def derive_display_name(model_id: str) -> str:
    """Strip the org prefix and replace `-` with spaces.

    Examples:
        Qwen/Qwen3-Embedding-8B            -> Qwen3 Embedding 8B
        BAAI/bge-large-en-v1.5             -> bge large en v1.5
        sentence-transformers/all-MiniLM   -> all MiniLM
    The intentional minimalism here matches the user's request: keep the
    repo's own casing and only drop the org segment plus dashes, so
    operators can hand-clean the manifest before import if needed.
    """
    last = model_id.rsplit("/", 1)[-1]
    if not last:
        return model_id
    return last.replace("-", " ").strip()


def extract_arxiv_id(meta: Any) -> Optional[str]:
    """Best-effort extraction of an arXiv id from a ModelMeta.

    Looks at `meta.citation` (BibTeX) first because that is the most
    explicit place authors put a paper reference, and falls back to
    `meta.reference` if it points to an arXiv URL.
    """
    citation = getattr(meta, "citation", None) or ""
    match = ARXIV_URL_RE.search(citation)
    if not match:
        match = re.search(r"arXiv preprint arXiv:\s*(\d{4}\.\d{4,5})", citation)
    if not match:
        match = re.search(r"\barXiv:\s*(\d{4}\.\d{4,5})", citation)
    if match:
        return match.group(1)

    reference = getattr(meta, "reference", None) or ""
    match = ARXIV_URL_RE.search(reference)
    if match:
        return match.group(1)
    return None


def model_meta_summary(meta: Any) -> dict[str, Any]:
    """Pick the metadata fields we want to surface in the preview/import.

    The follow-up schema migration adds matching columns on
    `evaluations`; the keys here intentionally match those proposed
    columns so the import step is a straight passthrough.
    """
    if meta is None:
        return {}
    return {
        "n_parameters": getattr(meta, "n_parameters", None),
        "n_active_parameters": getattr(meta, "n_active_parameters_override", None),
        "n_embedding_parameters": getattr(meta, "n_embedding_parameters", None),
        "memory_usage_mb": getattr(meta, "memory_usage_mb", None),
        "max_tokens": getattr(meta, "max_tokens", None),
        "embed_dim": getattr(meta, "embed_dim", None),
        "license": getattr(meta, "license", None),
        "open_weights": getattr(meta, "open_weights", None),
        "framework": list(getattr(meta, "framework", []) or []) or None,
        "languages": list(getattr(meta, "languages", []) or []) or None,
        "modalities": list(getattr(meta, "modalities", []) or []) or None,
        "model_type": list(getattr(meta, "model_type", []) or []) or None,
        "use_instructions": getattr(meta, "use_instructions", None),
        "model_reference_url": getattr(meta, "reference", None),
        "release_date": str(getattr(meta, "release_date", None) or "") or None,
    }


def jsonify(value: Any) -> Any:
    """Make a value JSON-serialisable for CSV output."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonify(v) for k, v in value.items()}
    return str(value)


# ---------------------------------------------------------------------------
# Paper resolution
# ---------------------------------------------------------------------------


@dataclass
class PaperResolution:
    model_id: str
    display_model_name: str
    resolution: str  # existing_arxiv | missing_arxiv_import_needed | existing_external | new_external | skipped
    arxiv_id: Optional[str] = None
    external_url: Optional[str] = None
    source_title: Optional[str] = None
    source_date: Optional[str] = None
    existing_paper_id: Optional[int] = None
    notes: str = ""


def resolve_paper_for_model(db, model_id: str, meta: Any) -> PaperResolution:
    """Decide which paper row this evaluation should attach to.

    Order of precedence (matches the agreed plan):

    1. arXiv id pulled out of the ModelMeta's citation/reference. If
       that paper exists in our DB we mark it `existing_arxiv` so the
       importer can reuse it. Otherwise we mark it
       `missing_arxiv_import_needed` rather than silently creating an
       external row, because we want to import the actual arxiv paper
       in a follow-up rather than orphan the evaluation on a HF page.
    2. Otherwise, an external paper row keyed by the HF model URL,
       only if we have a defensible release_date (mteb-shipped) on
       `meta`. Existing rows are reused.
    3. Otherwise we skip with a reason.
    """
    display = derive_display_name(model_id)
    hf_url = f"https://huggingface.co/{model_id}"

    arxiv_id = extract_arxiv_id(meta)
    if arxiv_id:
        existing = (
            db.query(DBPaper)
            .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version)
            .first()
        )
        if existing is not None:
            return PaperResolution(
                model_id=model_id,
                display_model_name=display,
                resolution="existing_arxiv",
                arxiv_id=arxiv_id,
                source_title=existing.title,
                source_date=str(existing.date_published or ""),
                existing_paper_id=existing.id,
            )
        return PaperResolution(
            model_id=model_id,
            display_model_name=display,
            resolution="missing_arxiv_import_needed",
            arxiv_id=arxiv_id,
            external_url=f"https://arxiv.org/abs/{arxiv_id}",
            source_date=str(getattr(meta, "release_date", None) or ""),
            notes="arXiv id from ModelMeta citation/reference not yet ingested",
        )

    release = getattr(meta, "release_date", None)
    if not release:
        return PaperResolution(
            model_id=model_id,
            display_model_name=display,
            resolution="skipped",
            external_url=hf_url,
            notes="No arXiv id and no release_date on ModelMeta; refusing to invent a paper",
        )

    existing_external = (
        db.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == hf_url)
        .first()
    )
    if existing_external is not None:
        return PaperResolution(
            model_id=model_id,
            display_model_name=display,
            resolution="existing_external",
            external_url=hf_url,
            source_title=existing_external.title,
            source_date=str(existing_external.date_published or ""),
            existing_paper_id=existing_external.id,
        )

    return PaperResolution(
        model_id=model_id,
        display_model_name=display,
        resolution="new_external",
        external_url=hf_url,
        source_title=model_id,
        source_date=str(release),
    )


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkRow:
    model_id: str
    display_model_name: str
    benchmark_name: str
    dataset_name: str
    task_slug: str  # task page slug this row belongs on (root or subtask)
    task_type: Optional[str]  # None for the aggregate row
    metric_name: str
    score: float
    evaluated_on: Optional[str]
    n_tasks: int
    methodology: str  # description of which tasks were averaged
    paper_resolution: PaperResolution
    model_meta: dict[str, Any] = field(default_factory=dict)


def _safe_get_score(task_result: Any) -> Optional[float]:
    """Some old result files raise on aggregation; treat those as missing."""
    try:
        return task_result.get_score()
    except Exception:
        return None


def compute_scores_for_benchmark(
    benchmark_name: str,
    dataset_name: str,
    cache: ResultCache,
) -> Iterable[
    tuple[
        str,
        dict[str, Any],
        dict[str, list[float]],
        dict[str, list[str]],
        Optional[date],
    ]
]:
    """For the given benchmark, yield per-model:

    (model_id, ModelMeta, task_type_to_scores, task_type_to_task_names, latest_eval_date)

    Only models with COMPLETE coverage of the benchmark are yielded so
    the aggregate matches MTEB's official `Mean(Task)` semantics.
    """
    benchmark = mteb.get_benchmark(benchmark_name)
    results = cache.load_results(
        tasks=benchmark, include_remote=False, require_model_meta=True
    )
    bench_results = results.join_revisions()
    expected_task_names = {t.metadata.name for t in benchmark.tasks}

    seen_models: set[str] = set()
    for model_result in bench_results:
        if model_result.model_name in seen_models:
            continue
        seen_models.add(model_result.model_name)

        filtered = model_result.select_tasks(benchmark.tasks).task_results
        type_to_scores: dict[str, list[float]] = defaultdict(list)
        type_to_tasks: dict[str, list[str]] = defaultdict(list)
        seen_task_names: set[str] = set()
        eval_dates: list[date] = []
        complete = True
        for tr in filtered:
            score = _safe_get_score(tr)
            if score is None:
                complete = False
                break
            seen_task_names.add(tr.task_name)
            type_to_scores[tr.task.metadata.type].append(score)
            type_to_tasks[tr.task.metadata.type].append(tr.task_name)
            eval_date = getattr(tr, "evaluation_time", None)
            if isinstance(eval_date, date):
                eval_dates.append(eval_date)

        if not complete:
            continue
        if seen_task_names != expected_task_names:
            continue

        meta = mteb.get_model_meta(model_result.model_name)
        latest_eval = max(eval_dates) if eval_dates else None
        yield (
            model_result.model_name,
            meta,
            type_to_scores,
            type_to_tasks,
            latest_eval,
        )


# ---------------------------------------------------------------------------
# Main preview generation
# ---------------------------------------------------------------------------


def main() -> None:
    cache_path = DEFAULT_CACHE_PATH
    if not (cache_path / "results").exists():
        sys.exit(
            f"mteb results cache missing at {cache_path}/results. Clone "
            "https://github.com/embeddings-benchmark/results.git first."
        )
    cache = ResultCache(cache_path)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Writing preview manifests to %s", PREVIEW_DIR)

    db = db_manager.session_local()
    try:
        paper_rows: dict[str, PaperResolution] = {}
        eval_rows: list[BenchmarkRow] = []
        skip_rows: list[dict[str, Any]] = []

        for benchmark_name, dataset_name in FEATURED_BENCHMARKS:
            logger.info("Processing benchmark %s (-> %s)", benchmark_name, dataset_name)
            for (
                model_id,
                meta,
                type_scores,
                type_tasks,
                latest_eval,
            ) in compute_scores_for_benchmark(benchmark_name, dataset_name, cache):
                resolution = paper_rows.get(model_id)
                if resolution is None:
                    resolution = resolve_paper_for_model(db, model_id, meta)
                    paper_rows[model_id] = resolution

                if resolution.resolution == "skipped":
                    skip_rows.append(
                        {
                            "model_id": model_id,
                            "display_model_name": resolution.display_model_name,
                            "benchmark_name": benchmark_name,
                            "reason": resolution.notes,
                        }
                    )
                    continue

                model_meta = model_meta_summary(meta)
                evaluated_on = (
                    str(latest_eval)
                    if latest_eval
                    else (model_meta.get("release_date") or "")
                )

                # Aggregate row: mean across all benchmark tasks.
                all_scores = [s for scores in type_scores.values() for s in scores]
                if not all_scores:
                    continue
                aggregate = sum(all_scores) / len(all_scores)
                eval_rows.append(
                    BenchmarkRow(
                        model_id=model_id,
                        display_model_name=resolution.display_model_name,
                        benchmark_name=benchmark_name,
                        dataset_name=dataset_name,
                        task_slug="embedding-models",
                        task_type=None,
                        metric_name="MTEB Score",
                        score=round(aggregate, 4),
                        evaluated_on=evaluated_on or None,
                        n_tasks=len(all_scores),
                        methodology=(
                            f"Mean over {len(all_scores)} {benchmark_name} tasks "
                            "(official MTEB aggregation, missing tasks excluded)."
                        ),
                        paper_resolution=resolution,
                        model_meta=model_meta,
                    )
                )

                # Per-task-type rollup rows. Skip task types that don't
                # map to a known subtask so we never create rows for a
                # taxonomy bucket we don't yet model.
                for task_type, scores in type_scores.items():
                    subtask_slug = TASK_TYPE_TO_SUBTASK_SLUG.get(task_type)
                    if subtask_slug is None:
                        skip_rows.append(
                            {
                                "model_id": model_id,
                                "display_model_name": resolution.display_model_name,
                                "benchmark_name": benchmark_name,
                                "reason": f"Unmapped task type '{task_type}' (no subtask slug)",
                            }
                        )
                        continue
                    if not scores:
                        continue
                    rollup = sum(scores) / len(scores)
                    eval_rows.append(
                        BenchmarkRow(
                            model_id=model_id,
                            display_model_name=resolution.display_model_name,
                            benchmark_name=benchmark_name,
                            dataset_name=dataset_name,
                            task_slug=subtask_slug,
                            task_type=task_type,
                            metric_name="MTEB Score",
                            score=round(rollup, 4),
                            evaluated_on=evaluated_on or None,
                            n_tasks=len(scores),
                            methodology=(
                                f"Mean over {len(scores)} {task_type} tasks within {benchmark_name}: "
                                + ", ".join(sorted(type_tasks[task_type]))
                            ),
                            paper_resolution=resolution,
                            model_meta=model_meta,
                        )
                    )

        # ------------------------------------------------------------------
        # Write papers manifest
        # ------------------------------------------------------------------
        papers_csv = PREVIEW_DIR / "mteb_papers.csv"
        with papers_csv.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "model_id",
                    "display_model_name",
                    "resolution",
                    "arxiv_id",
                    "external_url",
                    "source_title",
                    "source_date",
                    "existing_paper_id",
                    "notes",
                ]
            )
            for resolution in sorted(
                paper_rows.values(), key=lambda r: r.model_id.lower()
            ):
                writer.writerow(
                    [
                        resolution.model_id,
                        resolution.display_model_name,
                        resolution.resolution,
                        resolution.arxiv_id or "",
                        resolution.external_url or "",
                        resolution.source_title or "",
                        resolution.source_date or "",
                        resolution.existing_paper_id or "",
                        resolution.notes,
                    ]
                )
        logger.info("Wrote %d paper rows to %s", len(paper_rows), papers_csv)

        # ------------------------------------------------------------------
        # Write evaluations manifest
        # ------------------------------------------------------------------
        evals_csv = PREVIEW_DIR / "mteb_evaluations.csv"
        with evals_csv.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "model_id",
                    "display_model_name",
                    "paper_key",
                    "paper_resolution",
                    "task_slug",
                    "task_type",
                    "dataset_name",
                    "benchmark_name",
                    "metric_name",
                    "score",
                    "n_tasks",
                    "evaluated_on",
                    "methodology",
                    "external_source_url",
                    "model_meta_json",
                ]
            )
            for row in sorted(
                eval_rows,
                key=lambda r: (
                    r.benchmark_name,
                    r.task_slug,
                    -r.score,
                    r.model_id.lower(),
                ),
            ):
                paper_key = (
                    f"arxiv:{row.paper_resolution.arxiv_id}"
                    if row.paper_resolution.arxiv_id
                    else f"hf:{row.paper_resolution.external_url}"
                )
                writer.writerow(
                    [
                        row.model_id,
                        row.display_model_name,
                        paper_key,
                        row.paper_resolution.resolution,
                        row.task_slug,
                        row.task_type or "",
                        row.dataset_name,
                        row.benchmark_name,
                        row.metric_name,
                        row.score,
                        row.n_tasks,
                        row.evaluated_on or "",
                        row.methodology,
                        f"https://huggingface.co/{row.model_id}",
                        json.dumps(jsonify(row.model_meta), sort_keys=True),
                    ]
                )
        logger.info("Wrote %d evaluation rows to %s", len(eval_rows), evals_csv)

        # ------------------------------------------------------------------
        # Write skipped manifest
        # ------------------------------------------------------------------
        skipped_csv = PREVIEW_DIR / "mteb_skipped.csv"
        with skipped_csv.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["model_id", "display_model_name", "benchmark_name", "reason"]
            )
            for row in skip_rows:
                writer.writerow(
                    [
                        row["model_id"],
                        row["display_model_name"],
                        row["benchmark_name"],
                        row["reason"],
                    ]
                )
        logger.info("Wrote %d skipped rows to %s", len(skip_rows), skipped_csv)

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        from collections import Counter

        res_counter = Counter(r.resolution for r in paper_rows.values())
        logger.info("Paper resolution summary:")
        for k, v in sorted(res_counter.items()):
            logger.info("  %-32s %d", k, v)
        logger.info("Total candidate evaluations: %d", len(eval_rows))
        logger.info("Total skipped rows:           %d", len(skip_rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
