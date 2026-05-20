"""
Add Carbon evaluations (paper 83340) to the Biology benchmarks.

Source: "Carbon: Decoding the Language of Life" tech report
        https://github.com/huggingface/carbon/blob/main/tech-report.pdf

Imports the headline training-free evaluation scores from Tables 5–7 of the
tech report. Only writes rows for benchmarks where the source's reported
metric matches an Accuracy-configured leaderboard:

  * Sequence Recovery (next-token accuracy)        -> Accuracy
  * Genomic-NIAH @ 393 kbp YaRN (exact-match acc.) -> Accuracy
  * Perturbation Bench (pairwise discrimination acc.)
        - Nucleotide triplet-expansion             -> Accuracy
        - Synonymous codon                         -> Accuracy
        (encoded as separate rows with model_name suffixes per skill rule)

Skipped because the source metric is not configured on the leaderboard:

  * ClinVar VEP (AUROC)
  * TraitGym Mendelian (AUPRC by-chrom)

Also performs metadata cleanup:

  * Re-attributes Genomic-NIAH and Perturbation Bench to paper 83340 (the
    canonical Carbon tech report), since both benchmarks were introduced by
    this release. The previous placeholders (RULER for Genomic-NIAH, the
    deprecated "Carbon: Genomic Language Models" external row 83345 for
    Perturbation Bench) were stand-ins inserted when paper 83340 was not
    yet known to this script.
  * Deletes the now-unreferenced paper 83345.

Idempotent: safe to re-run.

Run:
    uv run --env-file backend/keys.env python scripts/add_carbon_evaluations.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
)
from backend.services.evaluation_service import EvaluationService


CARBON_PAPER_ID = 83340
OLD_CARBON_PLACEHOLDER_PAPER_ID = 83345
BIOLOGY_TASK_ID = 299

SEQUENCE_RECOVERY_DATASET_ID = 512
GENOMIC_NIAH_DATASET_ID = 511
PERTURBATION_BENCH_DATASET_ID = 514


@dataclass(frozen=True)
class EvalRow:
    dataset_id: int
    model_name: str
    score_pct: float
    methodology: str


CARBON_EVALS: list[EvalRow] = [
    # Sequence Recovery (Table 6 / 7 — eukaryote subset, primary generative
    # task; source metric: next-token nucleotide accuracy (%)).
    EvalRow(
        dataset_id=SEQUENCE_RECOVERY_DATASET_ID,
        model_name="Carbon-3B",
        score_pct=61.54,
        methodology=(
            "Sequence Recovery eukaryote subset, next-token nucleotide "
            "accuracy. Reported in Table 6 of the Carbon tech report. "
            "Training-free evaluation."
        ),
    ),
    EvalRow(
        dataset_id=SEQUENCE_RECOVERY_DATASET_ID,
        model_name="Carbon-8B",
        score_pct=64.05,
        methodology=(
            "Sequence Recovery eukaryote subset, next-token nucleotide "
            "accuracy. Reported in Table 7 of the Carbon tech report. "
            "Training-free evaluation."
        ),
    ),
    # Genomic-NIAH (Table 5 / 6 / 7 — plain retrieval, headline 393 kbp
    # number is reported in the main scoreboard; source metric: exact-match
    # retrieval accuracy).
    EvalRow(
        dataset_id=GENOMIC_NIAH_DATASET_ID,
        model_name="Carbon-3B",
        score_pct=79.00,
        methodology=(
            "Genomic-NIAH plain retrieval at 64k tokens (~393 kbp), exact-"
            "match accuracy. Native 32k context extended at inference with "
            "YaRN 2x; 500 examples per context length. Headline number from "
            "Table 6 of the Carbon tech report."
        ),
    ),
    EvalRow(
        dataset_id=GENOMIC_NIAH_DATASET_ID,
        model_name="Carbon-8B",
        score_pct=86.00,
        methodology=(
            "Genomic-NIAH plain retrieval at 64k tokens (~393 kbp), exact-"
            "match accuracy. Native 32k context extended at inference with "
            "YaRN 2x; 500 examples per context length. Headline number from "
            "Table 7 of the Carbon tech report."
        ),
    ),
    # Perturbation Bench — two subtasks reported separately in Tables 6/7
    # under the Perturbation Bench umbrella. Both use pairwise discrimination
    # accuracy. Encoded as separate rows with model_name suffixes per the
    # add-evals skill's rule for shared-metric subtask splits.
    EvalRow(
        dataset_id=PERTURBATION_BENCH_DATASET_ID,
        model_name="Carbon-3B (triplet expansion)",
        score_pct=85.20,
        methodology=(
            "Perturbation Bench: nucleotide triplet-expansion (CAG repeat "
            "insertion in human CDS, motif_human config). Pairwise "
            "discrimination accuracy = mean(LL(original) > LL(perturbed)). "
            "Table 6 of the Carbon tech report."
        ),
    ),
    EvalRow(
        dataset_id=PERTURBATION_BENCH_DATASET_ID,
        model_name="Carbon-3B (synonymous codon)",
        score_pct=88.89,
        methodology=(
            "Perturbation Bench: synonymous codon substitution in CDS "
            "(syn_human + syn_mouse configs). Pairwise discrimination "
            "accuracy = mean(LL(original) > LL(perturbed)). Table 6 of "
            "the Carbon tech report."
        ),
    ),
    EvalRow(
        dataset_id=PERTURBATION_BENCH_DATASET_ID,
        model_name="Carbon-8B (triplet expansion)",
        score_pct=89.05,
        methodology=(
            "Perturbation Bench: nucleotide triplet-expansion (CAG repeat "
            "insertion in human CDS, motif_human config). Pairwise "
            "discrimination accuracy = mean(LL(original) > LL(perturbed)). "
            "Table 7 of the Carbon tech report."
        ),
    ),
    EvalRow(
        dataset_id=PERTURBATION_BENCH_DATASET_ID,
        model_name="Carbon-8B (synonymous codon)",
        score_pct=91.46,
        methodology=(
            "Perturbation Bench: synonymous codon substitution in CDS "
            "(syn_human + syn_mouse configs). Pairwise discrimination "
            "accuracy = mean(LL(original) > LL(perturbed)). Table 7 of "
            "the Carbon tech report."
        ),
    ),
]


def reattribute_carbon_benchmarks(db) -> None:
    """Point Genomic-NIAH and Perturbation Bench at the real Carbon paper."""
    carbon = db.query(DBPaper).filter(DBPaper.id == CARBON_PAPER_ID).one_or_none()
    if not carbon:
        raise RuntimeError(f"Carbon tech report paper {CARBON_PAPER_ID} not found")

    paper_url = f"https://paperswithcode.co/paper/{carbon.arxiv_id or carbon.id}"

    for dataset_id in (GENOMIC_NIAH_DATASET_ID, PERTURBATION_BENCH_DATASET_ID):
        dataset = db.query(DBDataset).filter(DBDataset.id == dataset_id).one()
        if dataset.introducing_paper_id == carbon.id and dataset.paper_url == paper_url:
            continue
        dataset.introducing_paper_id = carbon.id
        dataset.introducing_paper_title = carbon.title
        dataset.paper_url = paper_url
        db.flush()
        print(
            f"  re-attributed dataset {dataset_id} ({dataset.name}) -> "
            f"paper {carbon.id}"
        )


def drop_placeholder_carbon_paper(db) -> None:
    """Delete the old placeholder Carbon paper if it is unreferenced."""
    placeholder = (
        db.query(DBPaper)
        .filter(DBPaper.id == OLD_CARBON_PLACEHOLDER_PAPER_ID)
        .one_or_none()
    )
    if not placeholder:
        return

    ref_count = db.execute(
        text("SELECT count(*) FROM datasets WHERE introducing_paper_id = :pid"),
        {"pid": placeholder.id},
    ).scalar_one()
    eval_count = db.execute(
        text("SELECT count(*) FROM evaluations WHERE paper_id = :pid"),
        {"pid": placeholder.id},
    ).scalar_one()

    if ref_count or eval_count:
        print(
            f"  placeholder paper {placeholder.id} still referenced "
            f"({ref_count} datasets, {eval_count} evals); not deleting"
        )
        return

    db.delete(placeholder)
    db.flush()
    print(f"  deleted unreferenced placeholder paper {OLD_CARBON_PLACEHOLDER_PAPER_ID}")


def get_existing_evaluation(
    db,
    *,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_name: str,
    harness: Optional[str],
    best_metric: str,
) -> Optional[DBEvaluation]:
    return (
        db.query(DBEvaluation)
        .filter(
            DBEvaluation.paper_id == paper_id,
            DBEvaluation.task_id == task_id,
            DBEvaluation.dataset_id == dataset_id,
            DBEvaluation.model_name == model_name,
            DBEvaluation.harness.is_(None)
            if harness is None
            else DBEvaluation.harness == harness,
            DBEvaluation.best_metric == best_metric,
        )
        .one_or_none()
    )


def post_evaluations(db) -> tuple[int, int]:
    service = EvaluationService(db)
    created = 0
    skipped = 0
    for row in CARBON_EVALS:
        existing = get_existing_evaluation(
            db,
            paper_id=CARBON_PAPER_ID,
            task_id=BIOLOGY_TASK_ID,
            dataset_id=row.dataset_id,
            model_name=row.model_name,
            harness=None,
            best_metric="Accuracy",
        )
        if existing:
            skipped += 1
            print(
                f"  exists: id={existing.id} dataset={row.dataset_id} "
                f"model='{row.model_name}' accuracy={row.score_pct}"
            )
            continue

        eva = service.create_evaluation(
            paper_id=CARBON_PAPER_ID,
            task_id=BIOLOGY_TASK_ID,
            dataset_id=row.dataset_id,
            model_name=row.model_name,
            harness=None,
            methodology=row.methodology,
            metrics={"Accuracy": f"{row.score_pct:.2f}"},
            best_metric="Accuracy",
            uses_additional_data=False,
        )
        created += 1
        print(
            f"  created: id={eva.id} dataset={row.dataset_id} "
            f"model='{row.model_name}' accuracy={row.score_pct}"
        )
    return created, skipped


def main() -> int:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        print("Re-attributing Carbon-native benchmarks to paper 83340...")
        reattribute_carbon_benchmarks(db)
        db.commit()

        print("\nCleaning up the placeholder Carbon paper...")
        drop_placeholder_carbon_paper(db)
        db.commit()

        print("\nPosting evaluations for paper 83340...")
        created, skipped = post_evaluations(db)
        print(f"\nDone. Created {created} new evaluations, {skipped} already existed.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
