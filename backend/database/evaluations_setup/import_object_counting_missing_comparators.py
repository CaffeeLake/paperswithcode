#!/usr/bin/env python3
"""Import CountSE, GroundingREC, TFPOC, DAVE, and CountGD++ PrACo evals."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

TASK_ID = 340
SOURCE = "CountGD++ Table comparison; arXiv:2512.23351"

# Resolve at runtime by arxiv / title
PAPER_ARXIV = {
    "countgdpp": "2512.23351",
    "dave": "2404.16622",
    "tfpoc": "2307.00038",
}

ROWS = [
    # Table 1 — FSC-147 text only (counting without detection)
    (
        "groundingrec",
        "GroundingREC",
        "FSC-147",
        "MAE",
        10.12,
        "Text-only positive prompt, Table 1",
    ),
    (
        "groundingrec",
        "GroundingREC",
        "FSC-147",
        "RMSE",
        107.19,
        "Text-only positive prompt, Table 1",
    ),
    (
        "countse",
        "CountSE",
        "FSC-147",
        "MAE",
        7.84,
        "Text-only positive prompt, Table 1",
    ),
    (
        "countse",
        "CountSE",
        "FSC-147",
        "RMSE",
        82.99,
        "Text-only positive prompt, Table 1",
    ),
    # Table 4 — ShanghaiTech Part A text only
    (
        "countse",
        "CountSE",
        "ShanghaiTech Part A",
        "MAE",
        129.7,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        "countse",
        "CountSE",
        "ShanghaiTech Part A",
        "RMSE",
        258.3,
        "Text-only positive prompt 'human', Table 4",
    ),
    # Table 3 — PrACo
    ("tfpoc", "TFPOC", "PrACo", "NMN", 0.75, "Positive text only, Table 3"),
    ("tfpoc", "TFPOC", "PrACo", "PCCN", 66.04, "Positive text only, Table 3"),
    ("tfpoc", "TFPOC", "PrACo", "CntP", 0.69, "Positive text only, Table 3"),
    ("tfpoc", "TFPOC", "PrACo", "CntR", 0.85, "Positive text only, Table 3"),
    ("dave", "DAVE", "PrACo", "NMN", 1.05, "Positive text only, Table 3"),
    ("dave", "DAVE", "PrACo", "PCCN", 37.02, "Positive text only, Table 3"),
    ("dave", "DAVE", "PrACo", "CntP", 0.84, "Positive text only, Table 3"),
    ("dave", "DAVE", "PrACo", "CntR", 0.80, "Positive text only, Table 3"),
    (
        "dave",
        "DAVE (with negatives)",
        "PrACo",
        "NMN",
        0.08,
        "Positive and negative text, Table 3",
    ),
    (
        "dave",
        "DAVE (with negatives)",
        "PrACo",
        "PCCN",
        97.62,
        "Positive and negative text, Table 3",
    ),
    (
        "dave",
        "DAVE (with negatives)",
        "PrACo",
        "CntP",
        0.84,
        "Positive and negative text, Table 3",
    ),
    (
        "dave",
        "DAVE (with negatives)",
        "PrACo",
        "CntR",
        0.80,
        "Positive and negative text, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++",
        "PrACo",
        "NMN",
        0.88,
        "Positive text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++",
        "PrACo",
        "PCCN",
        62.86,
        "Positive text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++",
        "PrACo",
        "CntP",
        0.86,
        "Positive text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++",
        "PrACo",
        "CntR",
        0.96,
        "Positive text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++ (with negatives)",
        "PrACo",
        "NMN",
        0.07,
        "Positive and negative text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++ (with negatives)",
        "PrACo",
        "PCCN",
        97.99,
        "Positive and negative text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++ (with negatives)",
        "PrACo",
        "CntP",
        0.90,
        "Positive and negative text + pseudo/synthetic exemplars, Table 3",
    ),
    (
        "countgdpp",
        "CountGD++ (with negatives)",
        "PrACo",
        "CntR",
        0.96,
        "Positive and negative text + pseudo/synthetic exemplars, Table 3",
    ),
]

DATASET_SLUG = {
    "FSC-147": "fsc-147",
    "FSCD-147": "fscd-147",
    "ShanghaiTech Part A": "shanghaitech-part-a",
    "PrACo": "praco",
}


def resolve_paper_ids(db) -> dict[str, int]:
    ids: dict[str, int] = {}
    for key, arxiv_id in PAPER_ARXIV.items():
        row = db.execute(
            text(
                "SELECT id FROM papers WHERE arxiv_id = :a AND is_latest_version LIMIT 1"
            ),
            {"a": arxiv_id},
        ).first()
        if not row:
            raise RuntimeError(f"Missing paper arxiv_id={arxiv_id}")
        ids[key] = int(row[0])

    for key, title_pat in [
        ("groundingrec", "%Referring Expression Counting%"),
        ("countse", "%CountSE: Soft Exemplar%"),
    ]:
        row = db.execute(
            text(
                """
                SELECT id FROM papers
                WHERE source = 'external' AND title ILIKE :t
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"t": title_pat},
        ).first()
        if not row:
            raise RuntimeError(f"Missing external paper matching {title_pat!r}")
        ids[key] = int(row[0])
    return ids


def resolve_dataset_ids(db) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, slug in DATASET_SLUG.items():
        row = db.execute(
            text("SELECT id FROM datasets WHERE slug = :s"), {"s": slug}
        ).first()
        if not row:
            raise RuntimeError(f"Missing dataset slug={slug!r}")
        out[label] = int(row[0])
    return out


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    created = skipped = 0
    try:
        paper_ids = resolve_paper_ids(db)
        dataset_ids = resolve_dataset_ids(db)
        svc = EvaluationService(db)
        for key, model_name, dataset_name, metric, score, note in ROWS:
            paper_id = paper_ids[key]
            dataset_id = dataset_ids[dataset_name]
            params = {
                "paper_id": paper_id,
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "best_metric": metric,
            }
            existing = db.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id=:paper_id AND task_id=:task_id AND dataset_id=:dataset_id
                      AND model_name=:model_name
                      AND COALESCE(harness, '') = ''
                      AND best_metric=:best_metric
                    """
                ),
                params,
            ).first()
            if existing:
                skipped += 1
                continue
            svc.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=f"{note}. {SOURCE}.",
                metrics={metric: score},
                best_metric=metric,
                external_source_url="https://arxiv.org/abs/2512.23351",
                is_open=True,
            )
            created += 1
        db.commit()
        print(f"created={created} skipped={skipped}")
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
