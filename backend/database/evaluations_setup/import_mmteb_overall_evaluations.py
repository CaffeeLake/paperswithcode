"""Import overall MMTEB Mean (Task) scores for the top-50 Multilingual leaderboard.

Apply-mode counterpart to `preview_mmteb_top50_overall.py`. Reuses that
module's `build_manifest()` (memory-safe top-50 fetch via the Space's
Gradio API on the Multilingual tab) and then:

1. Wires the `MMTEB` dataset (id 106) to the `Embedding models` task
   (id 17) via `task_datasets`, and backfills the dataset's paper
   attribution (`introducing_paper_id=44570` -> arxiv 2502.13595).
2. Ensures a `MMTEB Score` metric exists (higher_is_better) and links it
   to `(embedding-models, MMTEB)` in `task_dataset_metrics`.
3. For each `external_pending` candidate, finds or creates a single
   external `papers` row by `(source='external', source_url)`. The three
   titles (`Microsoft Harrier`, `Linq-Embed-Mistral`, `SFR-Embedding-
   Mistral`) already exist from the MTEB import, so they will be reused.
4. Posts one `evaluations` row per candidate via `EvaluationService`,
   storing the Mean (Task) score under the `MMTEB Score` metric.
5. Recalculates ranks for the (Embedding models, MMTEB, MMTEB Score)
   leaderboard.

Idempotent: re-running reuses existing benchmark wiring, external
papers, and skips duplicate evaluation rows per the unique constraint
`(paper_id, task_id, dataset_id, model_name, harness, best_metric)`.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_mmteb_overall_evaluations.py
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database.connection import db_manager
from backend.database.evaluations_setup.import_mteb_overall_evaluations import (
    EXTERNAL_PAPER_SPECS,
    ensure_metric,
    ensure_task_dataset,
    ensure_task_dataset_metric,
    get_or_create_external_paper,
)
from backend.database.evaluations_setup.preview_mmteb_top50_overall import (
    SPACE_ID,
    Candidate,
    build_manifest,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

EMBEDDING_MODELS_TASK_ID = 17
MMTEB_DATASET_ID = 106
MMTEB_PAPER_ID = (
    44570  # arxiv 2502.13595 "MMTEB: Massive Multilingual Text Embedding Benchmark"
)
MMTEB_PAPER_TITLE = "MMTEB: Massive Multilingual Text Embedding Benchmark"
MMTEB_PAPER_URL = "https://arxiv.org/abs/2502.13595"
MMTEB_INTRODUCED_YEAR = 2025
METRIC_NAME = "MMTEB Score"
METRIC_DIRECTION = "higher_is_better"
SPACE_URL = f"https://huggingface.co/spaces/{SPACE_ID}"


def ensure_dataset_paper_attribution(session) -> None:
    """Backfill MMTEB dataset (id 106) with its canonical introducing paper."""
    row = session.execute(
        text(
            "UPDATE datasets SET "
            "  introducing_paper_id = COALESCE(introducing_paper_id, :pid), "
            "  introducing_paper_title = COALESCE(introducing_paper_title, :title), "
            "  paper_url = COALESCE(paper_url, :url), "
            "  introduced_year = COALESCE(introduced_year, :year) "
            "WHERE id = :did "
            "RETURNING introducing_paper_id, introducing_paper_title, paper_url, introduced_year"
        ),
        {
            "pid": MMTEB_PAPER_ID,
            "title": MMTEB_PAPER_TITLE,
            "url": MMTEB_PAPER_URL,
            "year": MMTEB_INTRODUCED_YEAR,
            "did": MMTEB_DATASET_ID,
        },
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Dataset id={MMTEB_DATASET_ID} not found")
    logger.info(
        "Dataset %d paper attribution: introducing_paper_id=%s, year=%s",
        MMTEB_DATASET_ID,
        row[0],
        row[3],
    )


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
        # --- Wire benchmark + metric + paper attribution ---------------
        ensure_dataset_paper_attribution(session)
        ensure_task_dataset(session, EMBEDDING_MODELS_TASK_ID, MMTEB_DATASET_ID)
        metric_id = ensure_metric(session, METRIC_NAME, METRIC_DIRECTION)
        ensure_task_dataset_metric(
            session, EMBEDDING_MODELS_TASK_ID, MMTEB_DATASET_ID, metric_id
        )
        session.flush()
        logger.info(
            "Wired (task_id=%s, dataset_id=%s, metric_id=%s)",
            EMBEDDING_MODELS_TASK_ID,
            MMTEB_DATASET_ID,
            metric_id,
        )

        # --- External paper rows (reuse from MTEB run when present) ----
        external_titles: dict[str, list[str]] = {}
        for c in importable:
            if c.resolution != "external_pending":
                continue
            urls = external_titles.setdefault(c.paper_title, [])
            if c.model_url and c.model_url not in urls:
                urls.append(c.model_url)
        external_by_title = {}
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
                f"Overall Mean (Task) aggregate score from the MTEB leaderboard "
                f"Space ({SPACE_URL}) on the Multilingual / MMTEB benchmark, "
                f"top-{c.rank} row captured on {capture_date}."
            )
            try:
                eval_service.create_evaluation(
                    paper_id=paper_id,
                    task_id=EMBEDDING_MODELS_TASK_ID,
                    dataset_id=MMTEB_DATASET_ID,
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
            dataset_id=MMTEB_DATASET_ID,
            metric_name=METRIC_NAME,
        )
        session.commit()
        logger.info("Recalculated ranks: %d rows updated", updated)

        # --- Report ----------------------------------------------------
        print()
        print("=== MMTEB Overall Top-50 Import ===")
        print(f"Manifest candidates: {len(candidates)} (importable: {len(importable)})")
        print(f"Manifest skipped:    {len(skipped)}")
        print(
            f"Benchmark wiring:    task_id={EMBEDDING_MODELS_TASK_ID}, "
            f"dataset_id={MMTEB_DATASET_ID}, metric_id={metric_id} "
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
            f"?dataset_id={MMTEB_DATASET_ID}&page_size=100'"
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
        f"?dataset_id={MMTEB_DATASET_ID}&page_size=5"
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
