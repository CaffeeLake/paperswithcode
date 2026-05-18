"""Import overall MTEB Mean (Task) scores for the top-50 leaderboard models.

This is the apply-mode counterpart to
`preview_mteb_top50_overall.py`. It reuses that module's `build_manifest()`
function (memory-safe, top-50 only, overall aggregate only) and then:

1. Wires the `MTEB` dataset (id 105) to the `Embedding models` task
   (id 17) via `task_datasets`.
2. Ensures a `MTEB Score` metric exists (higher_is_better) and links it
   to `(embedding-models, MTEB)` in `task_dataset_metrics`.
3. For each `external_pending` candidate, finds or creates a single
   external `papers` row with the title supplied by the override.
4. Posts one `evaluations` row per candidate via `EvaluationService`,
   storing the Mean (Task) score under the `MTEB Score` metric.
5. Recalculates ranks for the (Embedding models, MTEB, MTEB Score)
   leaderboard.

Idempotent: re-running the importer reuses existing benchmark wiring,
external papers, and skips duplicate evaluation rows (per the unique
constraint `(paper_id, task_id, dataset_id, model_name, harness,
best_metric)`).

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_mteb_overall_evaluations.py
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.evaluations_setup.preview_mteb_top50_overall import (
    Candidate,
    SPACE_ID,
    build_manifest,
)
from backend.models.database import Paper as DBPaper
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

EMBEDDING_MODELS_TASK_ID = 17
MTEB_DATASET_ID = 105
METRIC_NAME = "MTEB Score"
METRIC_DIRECTION = "higher_is_better"

# Per-external-paper metadata. The title key must match the override
# value in `preview_mteb_top50_overall.MODEL_OVERRIDES`. `source_url` is
# the canonical HF page used for de-duplication via the partial unique
# index on `(source='external', source_url)`. `date_published` falls
# back to HF `createdAt` if left as None, but we hard-code a default per
# release for determinism.
EXTERNAL_PAPER_SPECS: dict[str, dict[str, str]] = {
    "Microsoft Harrier": {
        "source_url": "https://huggingface.co/microsoft/harrier-oss-v1-27b",
        "date_published_fallback": "2026-03-30",
    },
    "Linq-Embed-Mistral": {
        "source_url": "https://huggingface.co/Linq-AI-Research/Linq-Embed-Mistral",
        "date_published_fallback": "2024-05-29",
    },
    "SFR-Embedding-Mistral": {
        "source_url": "https://huggingface.co/Salesforce/SFR-Embedding-Mistral",
        "date_published_fallback": "2024-01-24",
    },
}


def ensure_metric(session: Session, name: str, direction: str) -> int:
    """Return the metric id, creating the row when missing."""
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"),
        {"name": name},
    ).fetchone()
    if row is not None:
        return int(row[0])

    new_id = session.execute(
        text(
            "INSERT INTO metrics (name, direction) "
            "VALUES (:name, :direction) RETURNING id"
        ),
        {"name": name, "direction": direction},
    ).scalar_one()
    logger.info("Created metric %r (id=%s, direction=%s)", name, new_id, direction)
    return int(new_id)


def ensure_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    """Idempotently link a dataset to a task."""
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:task_id, :dataset_id) "
            "ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def ensure_task_dataset_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    """Idempotently link a metric to a (task, dataset) leaderboard."""
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:task_id, :dataset_id, :metric_id) "
            "ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )


def get_or_create_external_paper(
    session: Session, title: str, spec: dict[str, str], hf_models: list[str]
) -> DBPaper:
    """Find an existing external paper by `(source='external', source_url)` or create one."""
    source_url = spec["source_url"]
    existing = (
        session.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == source_url)
        .first()
    )
    if existing is not None:
        # Append HF model URLs we have not yet recorded.
        existing_hf = list(existing.hf_models or [])
        for url in hf_models:
            if url and url not in existing_hf:
                existing_hf.append(url)
        existing.hf_models = existing_hf
        if existing.date_published is None:
            existing.date_published = _parse_date(spec["date_published_fallback"])
        return existing

    paper = DBPaper(
        title=title,
        abstract=None,
        arxiv_id=None,
        source="external",
        source_url=source_url,
        date_published=_parse_date(spec["date_published_fallback"]),
        is_latest_version=True,
        version="v1",
        urls_extracted=True,
        hf_models=sorted({url for url in [source_url, *hf_models] if url}),
    )
    session.add(paper)
    session.flush()
    logger.info(
        "Created external paper %r (id=%s, url=%s)", title, paper.id, source_url
    )
    return paper


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> None:
    capture_date = date.today().isoformat()
    candidates, skipped = build_manifest()
    importable: list[Candidate] = [
        c for c in candidates if c.resolution in ("local_arxiv", "external_pending")
    ]
    if not importable:
        logger.warning("No importable candidates from manifest; nothing to do")
        return

    session = db_manager.session_local()
    try:
        # --- Wire benchmark + metric -----------------------------------
        ensure_task_dataset(session, EMBEDDING_MODELS_TASK_ID, MTEB_DATASET_ID)
        metric_id = ensure_metric(session, METRIC_NAME, METRIC_DIRECTION)
        ensure_task_dataset_metric(
            session, EMBEDDING_MODELS_TASK_ID, MTEB_DATASET_ID, metric_id
        )
        session.flush()
        logger.info(
            "Wired (task_id=%s, dataset_id=%s, metric_id=%s)",
            EMBEDDING_MODELS_TASK_ID,
            MTEB_DATASET_ID,
            metric_id,
        )

        # --- Create external paper rows (one per unique title) ---------
        # Pre-aggregate every variant model URL per external title so a
        # consolidated paper (e.g. "Microsoft Harrier" covering 27b/0.6b
        # /270m) records all of them in `hf_models`.
        external_titles: dict[str, list[str]] = {}
        for c in importable:
            if c.resolution != "external_pending":
                continue
            urls = external_titles.setdefault(c.paper_title, [])
            if c.model_url and c.model_url not in urls:
                urls.append(c.model_url)
        external_by_title: dict[str, DBPaper] = {}
        for title, urls in external_titles.items():
            spec = EXTERNAL_PAPER_SPECS.get(title)
            if spec is None:
                raise RuntimeError(
                    f"No EXTERNAL_PAPER_SPECS entry for title {title!r}; "
                    "add one before re-running the importer."
                )
            external_by_title[title] = get_or_create_external_paper(
                session, title=title, spec=spec, hf_models=urls
            )
        external_paper_id_by_title = {
            t: int(p.id) for t, p in external_by_title.items()
        }
        # Commit wiring + external papers so a later per-row rollback
        # during evaluation insertion cannot undo them.
        session.commit()

        # --- Resolve paper_id per candidate ----------------------------
        candidate_with_paper: list[tuple[Candidate, int]] = []
        for c in importable:
            if c.resolution == "local_arxiv":
                if not c.paper_id:
                    logger.warning(
                        "Skipping rank %s %s: missing local paper id",
                        c.rank,
                        c.model_name,
                    )
                    continue
                candidate_with_paper.append((c, int(c.paper_id)))
            else:
                candidate_with_paper.append(
                    (c, external_paper_id_by_title[c.paper_title])
                )

        # --- Post evaluations ------------------------------------------
        eval_service = EvaluationService(session)
        created = 0
        skipped_existing = 0
        errors: list[tuple[Candidate, str]] = []
        for c, paper_id in candidate_with_paper:
            methodology = (
                f"Overall Mean (Task) aggregate score from the MTEB English "
                f"leaderboard (https://huggingface.co/spaces/{SPACE_ID}), "
                f"top-{c.rank} row captured on {capture_date}."
            )
            try:
                eval_service.create_evaluation(
                    paper_id=paper_id,
                    task_id=EMBEDDING_MODELS_TASK_ID,
                    dataset_id=MTEB_DATASET_ID,
                    model_name=c.model_name,
                    methodology=methodology,
                    metrics={METRIC_NAME: f"{c.score:.4f}"},
                    best_metric=METRIC_NAME,
                    external_source_url=c.model_url or None,
                )
            except IntegrityError:
                session.rollback()
                skipped_existing += 1
                continue
            except ValueError as exc:
                session.rollback()
                errors.append((c, f"ValueError: {exc}"))
                continue
            created += 1

        session.commit()
        logger.info(
            "Posted evaluations: created=%d, skipped_existing=%d, errors=%d",
            created,
            skipped_existing,
            len(errors),
        )
        if errors:
            for c, msg in errors:
                logger.error("  rank=%s %s -> %s", c.rank, c.model_name, msg)

        # --- Recalculate ranks -----------------------------------------
        updated = eval_service.recalculate_ranks(
            task_id=EMBEDDING_MODELS_TASK_ID,
            dataset_id=MTEB_DATASET_ID,
            metric_name=METRIC_NAME,
        )
        session.commit()
        logger.info("Recalculated ranks: %d rows updated", updated)

        # --- Report ----------------------------------------------------
        print()
        print("=== MTEB Overall Top-50 Import ===")
        print(f"Manifest candidates: {len(candidates)} (importable: {len(importable)})")
        print(f"Manifest skipped:    {len(skipped)}")
        print(
            f"Benchmark wiring:    task_id={EMBEDDING_MODELS_TASK_ID}, "
            f"dataset_id={MTEB_DATASET_ID}, metric_id={metric_id} "
            f"({METRIC_NAME}, {METRIC_DIRECTION})"
        )
        print(
            f"External papers:     {len(external_by_title)} "
            f"({', '.join(sorted(external_by_title))})"
        )
        print(f"Evaluations created: {created}")
        print(f"Evaluations skipped: {skipped_existing} (already present)")
        print(f"Evaluation errors:   {len(errors)}")
        print(
            f"Verify:              "
            f"curl -s 'http://localhost:8000/api/v1/evaluations/"
            f"?dataset_id={MTEB_DATASET_ID}&page_size=100'"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    _post_import_smoke()


def _post_import_smoke() -> None:
    """Hit the API to confirm the leaderboard is reachable, best-effort."""
    url = (
        f"http://localhost:8000/api/v1/evaluations/"
        f"?dataset_id={MTEB_DATASET_ID}&page_size=5"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            status = resp.status
    except urllib.error.URLError as exc:
        logger.warning("Post-import smoke check failed: %s", exc)
        return
    logger.info("Post-import smoke check: %s -> HTTP %s", url, status)


if __name__ == "__main__":
    main()
