"""
Import the Open ASR Leaderboard into the paperswithcode database.

The Hugging Face `hf-audio/open-asr-leaderboard` dataset is the official
leaderboard for English ASR. This importer is the only authority for
Automatic Speech Recognition evaluations: it deletes every existing ASR
evaluation row and rebuilds them from the leaderboard.

Pipeline:
1. Pull the official ranking from `hf datasets leaderboard hf-audio/open-asr-leaderboard`.
2. For each model, fetch `.eval_results/open_asr_leaderboard.yaml` from the
   model repo (either `main` or the leaderboard's submission PR ref) plus
   the model's HF `tags` (used for arxiv resolution) and `createdAt`.
3. Resolve a `papers` row per model. We first try to reuse an existing
   arxiv-backed paper using `MODEL_PAPER_HINTS` (verified by the model's
   own arxiv tags AND a paper row already in the DB). Models without a
   confident match fall back to a `source='external'` row keyed by the
   HF model URL.
4. Delete all existing evaluations on the ASR task and reinsert the
   parent (Open ASR Leaderboard) row plus one row per matched
   sub-benchmark (WER only). RTFx is consolidated into the parent row.
5. Recalculate ranks for every affected (task, dataset) leaderboard.
6. Garbage-collect orphan `source='external'` HF-model papers that are no
   longer referenced anywhere.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_open_asr_evaluations.py
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    PaperTask as DBPaperTask,
    Task as DBTask,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ASR_TASK_SLUG = "automatic-speech-recognition"
LEADERBOARD_DATASET_SLUG = "open-asr-leaderboard"
LEADERBOARD_REPO = "hf-audio/open-asr-leaderboard"
OPEN_ASR_SOURCE_URL = "https://paperswithcode.co/benchmark/open-asr-leaderboard"

# Map YAML `task_id` values from the Open ASR Leaderboard schema to the
# corresponding existing dataset slugs in our database. Only entries listed
# here are imported; unknown sub-benchmarks (e.g. `voxpopuli_cleaned_aa_wer`)
# are skipped and reported.
SUB_BENCHMARK_SLUG_BY_YAML_TASK = {
    "ami_wer": "ami-ihm",
    "common_voice_wer": "common-voice",
    "earnings22_wer": "earnings-22",
    "gigaspeech_wer": "gigaspeech",
    "librispeech_clean_wer": "librispeech-clean",
    "librispeech_other_wer": "librispeech-other",
    "spgispeech_wer": "spgispeech",
    "tedlium_wer": "tedlium",
    "voxpopuli_wer": "voxpopuli",
}

ASR_DATASET_SLUGS = [
    "open-asr-leaderboard",
    *sorted(set(SUB_BENCHMARK_SLUG_BY_YAML_TASK.values())),
]

# Curated mapping from a HF model_id prefix to the canonical paper's arxiv id.
# For each entry, we only reuse the arxiv-backed paper if BOTH:
#   1. the arxiv id is present in the model's HF `tags` list (defense against
#      mistaken curation), AND
#   2. that arxiv id resolves to an `is_latest_version` papers row in our DB.
# Anything not matched here falls back to a `source='external'` paper keyed by
# the HF model URL (for genuinely paperless models like CohereLabs/Symphony).
# Order matters: longer/more specific prefixes are listed first so they win.
MODEL_PAPER_HINTS: list[tuple[str, str]] = [
    ("ibm-granite/granite-4.0-1b-speech", "2505.08699"),
    ("ibm-granite/granite-speech", "2505.08699"),
    ("microsoft/Phi-4-multimodal", "2503.01743"),
    ("openai/whisper", "2212.04356"),
    ("distil-whisper/", "2311.00430"),
    ("facebook/wav2vec2-conformer", "2010.05171"),
    ("facebook/wav2vec2", "2006.11477"),
    ("facebook/hubert", "2106.07447"),
    ("facebook/data2vec-audio", "2202.03555"),
    ("facebook/mms", "2305.13516"),
    ("mistralai/Voxtral", "2507.13264"),
    ("UsefulSensors/moonshine", "2410.15608"),
    ("nyrahealth/CrisperWhisper", "2408.16589"),
    ("nvidia/canary-qwen", "2503.05931"),
    ("nvidia/canary-1b", "2503.05931"),
    ("nvidia/canary-180m", "2503.05931"),
    ("nvidia/parakeet-tdt", "2304.06795"),
    ("nvidia/parakeet-rnnt", "2305.05084"),
    ("nvidia/parakeet-ctc", "2305.05084"),
    ("nvidia/stt_en_fastconformer", "2305.05084"),
    ("nvidia/stt_en_conformer", "2005.08100"),
]

# Explicit per-model overrides where the canonical arXiv paper is not declared
# as an `arxiv:` tag on the HF model card, or the model tags multiple arXiv
# ids and `resolve_canonical_paper` would otherwise leave it ambiguous. Unlike
# MODEL_PAPER_HINTS these win unconditionally as long as the arXiv paper is
# present in our DB. Key is the exact HF model_id (case-sensitive).
MODEL_PAPER_OVERRIDES: dict[str, str] = {
    "espnet/owsm_ctc_v3.1_1B": "2401.16658",
    "espnet/owsm_ctc_v4_1B": "2506.00338",
}

# External-family canonicalization. When a HF model_id matches one of these
# entries, the importer reuses the canonical model's `source='external'`
# paper row instead of creating a per-variant one. Each evaluation still
# carries the variant-specific `external_source_url`, so leaderboard rows
# keep tracing the right HF model in methodology. Key is the variant model_id, value is
# the canonical model_id that owns the consolidated paper row.
MODEL_FAMILY_CANONICAL: dict[str, str] = {
    "UsefulSensors/moonshine-streaming-tiny": (
        "UsefulSensors/moonshine-streaming-medium"
    ),
    "UsefulSensors/moonshine-streaming-small": (
        "UsefulSensors/moonshine-streaming-medium"
    ),
    "abr-ai/niagara-19m-batch.en": "abr-ai/niagara-38m-batch.en",
}


def derive_model_name(model_id: str) -> str:
    """Convert a HF repo id to the human-readable name used on the model card.

    The convention is the last path segment with the first letter
    capitalized so that lowercase repo names look presentable while
    mixed-case repos are left untouched.

    Examples:
      openai/whisper-large-v3            -> Whisper-large-v3
      ibm-granite/granite-4.0-1b-speech  -> Granite-4.0-1b-speech
      mistralai/Voxtral-Mini-3B-2507     -> Voxtral-Mini-3B-2507
      Qwen/Qwen3-ASR-1.7B                -> Qwen3-ASR-1.7B
    """
    last = model_id.rsplit("/", 1)[-1]
    if not last:
        return model_id
    return last[0].upper() + last[1:]


@dataclass
class ModelEntry:
    model_id: str
    rank: int
    mean_wer: float
    pull_request: Optional[int]
    yaml_url: str
    raw_yaml: Optional[str] = None
    yaml_records: list[dict] = field(default_factory=list)
    eval_date: Optional[date] = None
    created_at: Optional[date] = None
    arxiv_tags: list[str] = field(default_factory=list)
    fetch_error: Optional[str] = None


def fetch_leaderboard() -> list[ModelEntry]:
    """Fetch the official leaderboard via the `hf` CLI."""
    cmd = [
        "hf",
        "datasets",
        "leaderboard",
        LEADERBOARD_REPO,
        "--limit",
        "200",
        "--format",
        "json",
    ]
    logger.info("Fetching leaderboard via: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    rows = json.loads(proc.stdout)
    entries: list[ModelEntry] = []
    for row in rows:
        pr = row.get("pull_request")
        if pr:
            yurl = (
                f"https://huggingface.co/{row['model_id']}"
                f"/resolve/refs%2Fpr%2F{pr}/.eval_results/open_asr_leaderboard.yaml"
            )
        else:
            yurl = (
                f"https://huggingface.co/{row['model_id']}"
                "/resolve/main/.eval_results/open_asr_leaderboard.yaml"
            )
        entries.append(
            ModelEntry(
                model_id=row["model_id"],
                rank=row["rank"],
                mean_wer=float(row["value"]),
                pull_request=pr,
                yaml_url=yurl,
            )
        )
    logger.info("Leaderboard returned %d models", len(entries))
    return entries


def http_get(url: str, *, timeout: int = 20) -> Optional[str]:
    token = os.environ.get("PWC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _record_dates(records: list[dict]) -> Optional[date]:
    """Return the most recent `date` value across YAML/eval-results records."""
    dates: list[date] = []
    for rec in records:
        d = rec.get("date")
        if isinstance(d, date):
            dates.append(d)
        elif isinstance(d, str):
            try:
                dates.append(datetime.fromisoformat(d).date())
            except ValueError:
                continue
    return max(dates) if dates else None


def load_yaml_for_entry(entry: ModelEntry) -> None:
    try:
        text_yaml = http_get(entry.yaml_url, timeout=30)
    except urllib.error.HTTPError as exc:
        entry.fetch_error = f"HTTP {exc.code}"
        return
    except Exception as exc:
        entry.fetch_error = f"{type(exc).__name__}: {exc}"
        return

    entry.raw_yaml = text_yaml
    try:
        records = list(yaml.safe_load(text_yaml) or [])
    except yaml.YAMLError as exc:
        entry.fetch_error = f"YAML parse error: {exc}"
        return

    entry.yaml_records = records
    most_recent = _record_dates(records)
    if most_recent is not None:
        entry.eval_date = most_recent


def load_model_metadata(entry: ModelEntry) -> None:
    """Populate `entry.created_at`, `entry.arxiv_tags` and (optionally)
    `entry.yaml_records` from HF model_info.

    The `?expand=evalResults` payload mirrors the same eval entries that live
    in `.eval_results/open_asr_leaderboard.yaml` (one record per
    `(dataset, task_id)` pair). When the YAML fetch failed - e.g. the model
    repo is gated and the local token has not been granted access yet, or the
    file is temporarily unavailable - we fall back to those records so the
    importer still produces sub-benchmark rows instead of only the aggregate
    Mean WER from the leaderboard JSON.
    """
    # `expand` filters the response down to a fixed set of keys, so we have to
    # request every field we read below (tags, createdAt) in addition to
    # `evalResults`. Otherwise the recovered records arrive at the cost of
    # losing the model's HF tags and creation date.
    url = (
        f"https://huggingface.co/api/models/{entry.model_id}"
        "?expand=evalResults&expand=tags&expand=createdAt"
    )
    try:
        body = http_get(url, timeout=15)
    except Exception as exc:  # gated/private models can 401, etc.
        logger.warning("HF model_info fetch failed for %s: %s", entry.model_id, exc)
        return
    info = json.loads(body)
    entry.arxiv_tags = [
        t.split(":", 1)[1]
        for t in (info.get("tags") or [])
        if isinstance(t, str) and t.startswith("arxiv:")
    ]
    if not entry.yaml_records:
        eval_results = info.get("evalResults") or []
        records = [
            er["data"] for er in eval_results if isinstance(er.get("data"), dict)
        ]
        if records:
            entry.yaml_records = records
            most_recent = _record_dates(records)
            if most_recent is not None and entry.eval_date is None:
                entry.eval_date = most_recent
            if entry.fetch_error:
                entry.fetch_error = (
                    f"{entry.fetch_error} (recovered via HF evalResults)"
                )
    created = info.get("createdAt")
    if not created:
        return
    try:
        entry.created_at = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").date()
    except ValueError:
        try:
            entry.created_at = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            ).date()
        except ValueError:
            return


def resolve_canonical_paper(db: Session, entry: ModelEntry) -> Optional[DBPaper]:
    """Try to reuse an existing arxiv-backed paper for this HF model.

    Resolution order:

    1. `MODEL_PAPER_OVERRIDES` wins outright. This is the explicit per-model
       curation path for models whose arXiv id is missing from (or
       ambiguous in) their HF tags.
    2. Look up every `arxiv:` tag from the model's HF metadata in our local
       `papers` table. If exactly one tag resolves to a latest paper, reuse
       it. This covers the common case where the HF model card already
       declares its canonical paper and we just need to honor that link
       instead of fabricating an `source='external'` row.
    3. When the HF tags are ambiguous (multiple resolve) or the single
       resolved match disagrees with curation, fall back to the curated
       `MODEL_PAPER_HINTS` mapping as a tie-breaker so well-known model
       families keep pointing at the intended paper.
    4. Otherwise return None and the caller creates an external paper row.

    In all success paths the HF model URL is appended to the resolved
    paper's `hf_models` for traceability.
    """
    arxiv_set = set(entry.arxiv_tags)

    chosen: Optional[DBPaper] = None

    override_arxiv = MODEL_PAPER_OVERRIDES.get(entry.model_id)
    if override_arxiv:
        chosen = (
            db.query(DBPaper)
            .filter(
                DBPaper.arxiv_id == override_arxiv,
                DBPaper.is_latest_version,
            )
            .first()
        )

    candidates: list[DBPaper] = []
    if chosen is None and arxiv_set:
        candidates = (
            db.query(DBPaper)
            .filter(
                DBPaper.arxiv_id.in_(arxiv_set),
                DBPaper.is_latest_version,
            )
            .all()
        )

    if chosen is None and len(candidates) == 1:
        chosen = candidates[0]

    if chosen is None:
        model_lower = entry.model_id.lower()
        for prefix, arxiv_id in MODEL_PAPER_HINTS:
            if not model_lower.startswith(prefix.lower()):
                continue
            if arxiv_id not in arxiv_set:
                continue
            hint_match = next((c for c in candidates if c.arxiv_id == arxiv_id), None)
            if hint_match is None:
                hint_match = (
                    db.query(DBPaper)
                    .filter(
                        DBPaper.arxiv_id == arxiv_id,
                        DBPaper.is_latest_version,
                    )
                    .first()
                )
            if hint_match is not None:
                chosen = hint_match
                break

    if chosen is None:
        return None

    hf_url = f"https://huggingface.co/{entry.model_id}"
    existing_hf = list(chosen.hf_models or [])
    if hf_url not in existing_hf:
        existing_hf.append(hf_url)
        chosen.hf_models = existing_hf
    return chosen


def get_or_create_external_paper(
    db: Session, model_id: str, *, date_published: date
) -> DBPaper:
    """Return the external `papers` row for a HF model, creating it if needed.

    Uniqueness is enforced by the partial index on
    `(source='external', source_url)`; we key on the canonical HF model URL,
    falling back to a `MODEL_FAMILY_CANONICAL` override when this model_id
    is a variant of a consolidated family row (e.g. moonshine-streaming
    -tiny/-small both reuse the -medium row).
    """
    canonical_model_id = MODEL_FAMILY_CANONICAL.get(model_id, model_id)
    canonical_url = f"https://huggingface.co/{canonical_model_id}"
    variant_url = f"https://huggingface.co/{model_id}"

    existing = (
        db.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == canonical_url)
        .first()
    )
    if existing is not None:
        if existing.date_published is None:
            existing.date_published = date_published
        existing_hf = list(existing.hf_models or [])
        for url in {canonical_url, variant_url}:
            if url not in existing_hf:
                existing_hf.append(url)
        existing.hf_models = existing_hf
        return existing

    paper = DBPaper(
        title=canonical_model_id,
        abstract=None,
        arxiv_id=None,
        source="external",
        source_url=canonical_url,
        date_published=date_published,
        is_latest_version=True,
        version="v1",
        urls_extracted=True,
        hf_models=sorted({canonical_url, variant_url}),
    )
    db.add(paper)
    db.flush()
    return paper


def cleanup_orphan_external_hf_papers(db: Session) -> int:
    """Delete external `papers` rows that point at a HF model URL but have no
    remaining references. Useful after re-running the importer with smarter
    paper resolution: previously-created external rows for models that now
    map to an arxiv paper are no longer referenced and should be cleaned up.

    Returns the number of papers deleted.
    """
    result = db.execute(
        text(
            r"""
            DELETE FROM papers p
            WHERE p.source = 'external'
              AND p.source_url ~ '^https://huggingface\.co/[^/]+/[^/]+$'
              AND p.source_url NOT LIKE 'https://huggingface.co/papers/%'
              AND p.source_url NOT LIKE 'https://huggingface.co/datasets/%'
              AND p.source_url NOT LIKE 'https://huggingface.co/spaces/%'
              AND NOT EXISTS (SELECT 1 FROM evaluations e WHERE e.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_tasks pt WHERE pt.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_methods pm WHERE pm.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_datasets pd WHERE pd.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_repositories pr WHERE pr.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM paper_project_pages pp WHERE pp.paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM methods m WHERE m.source_paper_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM datasets d WHERE d.introducing_paper_id = p.id)
            """
        )
    )
    return result.rowcount or 0


def lookup_dataset_ids(db: Session) -> dict[str, int]:
    rows = db.execute(
        text("SELECT slug, id FROM datasets WHERE slug = ANY(:slugs)"),
        {"slugs": ASR_DATASET_SLUGS},
    ).fetchall()
    return {slug: id_ for slug, id_ in rows}


@dataclass
class ImportSummary:
    total_models: int = 0
    parent_rows_created: int = 0
    sub_rows_created: int = 0
    arxiv_papers_reused: int = 0
    external_papers_created: int = 0
    external_papers_reused: int = 0
    orphan_external_papers_deleted: int = 0
    arxiv_resolutions: list[tuple[str, str]] = field(default_factory=list)
    external_fallbacks: list[str] = field(default_factory=list)
    skipped_models: list[tuple[str, str]] = field(default_factory=list)
    skipped_subs: list[tuple[str, str, str]] = field(default_factory=list)


def main() -> None:
    summary = ImportSummary()
    entries = fetch_leaderboard()
    summary.total_models = len(entries)

    logger.info("Fetching .eval_results YAML for each model...")
    for entry in entries:
        load_yaml_for_entry(entry)
        if entry.fetch_error:
            logger.warning(
                "  %s (rank %s): YAML fetch failed (%s) - falling back to leaderboard mean WER only",
                entry.model_id,
                entry.rank,
                entry.fetch_error,
            )

    logger.info("Fetching HF model metadata (createdAt + arxiv tags)...")
    for entry in entries:
        load_model_metadata(entry)

    session = db_manager.session_local()
    try:
        asr_task = session.query(DBTask).filter(DBTask.slug == ASR_TASK_SLUG).first()
        if asr_task is None:
            raise RuntimeError(f"Task '{ASR_TASK_SLUG}' missing from database")

        dataset_ids = lookup_dataset_ids(session)
        parent_dataset_id = dataset_ids.get(LEADERBOARD_DATASET_SLUG)
        if parent_dataset_id is None:
            raise RuntimeError(
                f"Dataset '{LEADERBOARD_DATASET_SLUG}' missing from database"
            )

        # 1. Wipe existing ASR evaluations.
        existing_count = (
            session.query(DBEvaluation)
            .filter(DBEvaluation.task_id == asr_task.id)
            .count()
        )
        logger.info(
            "Deleting %d existing evaluations on task '%s' (id=%s)...",
            existing_count,
            asr_task.name,
            asr_task.id,
        )
        session.query(DBEvaluation).filter(DBEvaluation.task_id == asr_task.id).delete(
            synchronize_session=False
        )
        session.flush()

        # 2. Insert fresh evaluations.
        affected_leaderboards: set[tuple[int, int]] = set()
        tagged_paper_ids: set[int] = set()
        for entry in entries:
            # Pick a publication date for the source row, preferring the
            # model's HF createdAt and falling back to the YAML eval date.
            date_published = entry.created_at or entry.eval_date or date.today()

            paper = resolve_canonical_paper(session, entry)
            if paper is not None:
                summary.arxiv_papers_reused += 1
                summary.arxiv_resolutions.append(
                    (entry.model_id, paper.arxiv_id or "?")
                )
            else:
                canonical_model_id = MODEL_FAMILY_CANONICAL.get(
                    entry.model_id, entry.model_id
                )
                existed_before = (
                    session.query(DBPaper.id)
                    .filter(
                        DBPaper.source == "external",
                        DBPaper.source_url
                        == f"https://huggingface.co/{canonical_model_id}",
                    )
                    .first()
                    is not None
                )
                paper = get_or_create_external_paper(
                    session, entry.model_id, date_published=date_published
                )
                if existed_before:
                    summary.external_papers_reused += 1
                else:
                    summary.external_papers_created += 1
                summary.external_fallbacks.append(entry.model_id)

            if paper.id not in tagged_paper_ids:
                existing_tag = (
                    session.query(DBPaperTask)
                    .filter(
                        DBPaperTask.paper_id == paper.id,
                        DBPaperTask.task_id == asr_task.id,
                    )
                    .first()
                )
                if existing_tag is None:
                    session.add(
                        DBPaperTask(
                            paper_id=paper.id,
                            task_id=asr_task.id,
                            source="manual",
                        )
                    )
                tagged_paper_ids.add(paper.id)

            model_name = derive_model_name(entry.model_id)

            # Group YAML rows by task_id -> value.
            yaml_values: dict[str, float] = {}
            for rec in entry.yaml_records:
                ds = rec.get("dataset") or {}
                if ds.get("id") != LEADERBOARD_REPO:
                    continue
                tid = ds.get("task_id")
                val = rec.get("value")
                if tid and val is not None:
                    try:
                        yaml_values[tid] = float(val)
                    except (TypeError, ValueError):
                        continue

            # Always trust the leaderboard JSON for mean_wer; the HF
            # leaderboard authority overrides any drift in the YAML.
            yaml_values["mean_wer"] = entry.mean_wer

            # Methodology line traces back to the source.
            if entry.pull_request:
                ref_label = f"refs/pr/{entry.pull_request}"
            else:
                ref_label = "main"
            methodology = (
                f"Open ASR Leaderboard rank {entry.rank}; sourced from "
                f"{entry.model_id}/.eval_results/open_asr_leaderboard.yaml "
                f"({ref_label})"
            )
            if entry.fetch_error and not entry.yaml_records:
                methodology = (
                    f"Open ASR Leaderboard rank {entry.rank}; mean WER from "
                    f"hf-audio/open-asr-leaderboard JSON "
                    f"(YAML unavailable: {entry.fetch_error})"
                )
            elif entry.fetch_error and entry.yaml_records:
                methodology = (
                    f"Open ASR Leaderboard rank {entry.rank}; sub-benchmark "
                    f"scores recovered from huggingface.co/api/models/"
                    f"{entry.model_id}?expand=evalResults "
                    f"(YAML fetch: {entry.fetch_error})"
                )

            # Parent row: always present, includes mean WER and (optionally)
            # RTFx in the same metrics blob.
            parent_metrics = {"WER": f"{yaml_values['mean_wer']}"}
            if "rtfx" in yaml_values:
                parent_metrics["RTFx"] = f"{yaml_values['rtfx']}"
            session.add(
                DBEvaluation(
                    paper_id=paper.id,
                    task_id=asr_task.id,
                    dataset_id=parent_dataset_id,
                    model_name=model_name,
                    methodology=methodology,
                    metrics=parent_metrics,
                    best_metric="WER",
                    evaluated_on=entry.eval_date,
                    external_source_url=OPEN_ASR_SOURCE_URL,
                    source_url=OPEN_ASR_SOURCE_URL,
                    external=True,
                    hf_model_url=f"https://huggingface.co/{entry.model_id}",
                )
            )
            summary.parent_rows_created += 1
            affected_leaderboards.add((asr_task.id, parent_dataset_id))

            # Sub-benchmark WER rows.
            for yaml_task_id, slug in SUB_BENCHMARK_SLUG_BY_YAML_TASK.items():
                if yaml_task_id not in yaml_values:
                    continue
                ds_id = dataset_ids.get(slug)
                if ds_id is None:
                    summary.skipped_subs.append(
                        (entry.model_id, yaml_task_id, "dataset slug missing")
                    )
                    continue
                session.add(
                    DBEvaluation(
                        paper_id=paper.id,
                        task_id=asr_task.id,
                        dataset_id=ds_id,
                        model_name=model_name,
                        methodology=methodology,
                        metrics={"WER": f"{yaml_values[yaml_task_id]}"},
                        best_metric="WER",
                        evaluated_on=entry.eval_date,
                        external_source_url=OPEN_ASR_SOURCE_URL,
                        source_url=OPEN_ASR_SOURCE_URL,
                        external=True,
                        hf_model_url=f"https://huggingface.co/{entry.model_id}",
                    )
                )
                summary.sub_rows_created += 1
                affected_leaderboards.add((asr_task.id, ds_id))

            # Report any YAML sub-benchmarks that don't map to a known DB slug
            # so we can curate them later if desired.
            for yaml_task_id in yaml_values:
                if yaml_task_id in {"mean_wer", "rtfx"}:
                    continue
                if yaml_task_id not in SUB_BENCHMARK_SLUG_BY_YAML_TASK:
                    summary.skipped_subs.append(
                        (entry.model_id, yaml_task_id, "no DB mapping")
                    )

            if entry.fetch_error:
                summary.skipped_models.append((entry.model_id, entry.fetch_error))

        session.commit()
        logger.info(
            "Inserted %d parent rows + %d sub-benchmark rows",
            summary.parent_rows_created,
            summary.sub_rows_created,
        )

        # 3. Recalculate ranks for every affected leaderboard.
        eval_service = EvaluationService(session)
        for tid, did in sorted(affected_leaderboards):
            updated = eval_service.recalculate_ranks(tid, did)
            logger.info(
                "Recalculated %d ranks for task=%s, dataset=%s", updated, tid, did
            )

        # 4. Garbage-collect any external HF-model paper rows that the new
        #    arxiv-aware resolution made obsolete. Safe because the cleanup
        #    only touches rows with no remaining references anywhere.
        deleted = cleanup_orphan_external_hf_papers(session)
        summary.orphan_external_papers_deleted = deleted
        if deleted:
            logger.info("Deleted %d orphan external HF-model paper rows", deleted)
        session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # Final report.
    logger.info("=" * 70)
    logger.info("IMPORT SUMMARY")
    logger.info("=" * 70)
    logger.info("Models on leaderboard          : %d", summary.total_models)
    logger.info("Arxiv-backed papers reused     : %d", summary.arxiv_papers_reused)
    logger.info(
        "External papers (created/reused): %d / %d",
        summary.external_papers_created,
        summary.external_papers_reused,
    )
    logger.info(
        "Orphan external papers deleted : %d", summary.orphan_external_papers_deleted
    )
    logger.info("Parent (Open ASR) rows         : %d", summary.parent_rows_created)
    logger.info("Sub-benchmark rows             : %d", summary.sub_rows_created)

    if summary.arxiv_resolutions:
        logger.info("Arxiv paper attributions:")
        for model, arxiv in sorted(summary.arxiv_resolutions):
            logger.info("  %-60s -> arxiv:%s", model, arxiv)
    if summary.external_fallbacks:
        logger.info("External fallback (no canonical arxiv):")
        for m in sorted(summary.external_fallbacks):
            logger.info("  %s", m)

    if summary.skipped_models:
        logger.info("YAML-unavailable models (still got mean WER):")
        for m, reason in summary.skipped_models:
            logger.info("  - %s : %s", m, reason)

    if summary.skipped_subs:
        unmapped = sorted(
            {k[1] for k in summary.skipped_subs if k[2] == "no DB mapping"}
        )
        if unmapped:
            logger.info("YAML sub-benchmarks not mapped to DB datasets:")
            for k in unmapped:
                logger.info("  - %s", k)

    logger.info("Local task page: https://paperswithcode.co/tasks/%s", ASR_TASK_SLUG)
    logger.info(
        "Local benchmark page: https://paperswithcode.co/datasets/%s",
        LEADERBOARD_DATASET_SLUG,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Importer failed: %s", exc)
        sys.exit(1)
