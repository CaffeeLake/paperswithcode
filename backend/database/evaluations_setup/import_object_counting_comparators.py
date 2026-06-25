#!/usr/bin/env python3
"""Import object-counting comparator evals from CountGD++ (2512.23351) comparison tables."""

from __future__ import annotations

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

TASK_ID = 340
DATASET = {
    "FSC-147": "fsc-147",
    "FSCD-147": "fscd-147",
    "ShanghaiTech Part A": "shanghaitech-part-a",
    "ShanghaiTech Part B": "shanghaitech-part-b",
    "OmniCount (Fruits)": "omnicount-fruits",
    "Blood Cell Detection": "blood-cell-detection",
    "VideoCount (Crystals)": "videocount-crystals",
    "PairTally": "pairtally",
}

# paper_id -> list of eval dicts
# Scores from CountGD++ arXiv:2512.23351 Tables 1, 2, 4, 5, A.1 (text-only / stated prompt setup).
SOURCE = "CountGD++ Table comparison; arXiv:2512.23351"

ROWS = [
    # Table 1 — FSC-147 / FSCD-147 text only
    (
        98350,
        "DAVE (density)",
        "FSC-147",
        "MAE",
        14.90,
        "Text-only positive prompt; density branch (DAVE_prm), Table 1",
    ),
    (
        98350,
        "DAVE (density)",
        "FSC-147",
        "RMSE",
        103.42,
        "Text-only positive prompt; density branch (DAVE_prm), Table 1",
    ),
    (
        98350,
        "DAVE (detection)",
        "FSCD-147",
        "MAE",
        15.52,
        "Text-only positive prompt; detection branch, Table 1",
    ),
    (
        98350,
        "DAVE (detection)",
        "FSCD-147",
        "RMSE",
        114.10,
        "Text-only positive prompt; detection branch, Table 1",
    ),
    (
        98350,
        "DAVE (detection)",
        "FSCD-147",
        "AP",
        18.50,
        "Text-only positive prompt; detection branch, Table 1",
    ),
    (
        98350,
        "DAVE (detection)",
        "FSCD-147",
        "AP50",
        50.24,
        "Text-only positive prompt; detection branch, Table 1",
    ),
    (34211, "CountGD", "FSC-147", "MAE", 12.98, "Text-only positive prompt, Table 1"),
    (34211, "CountGD", "FSC-147", "RMSE", 98.35, "Text-only positive prompt, Table 1"),
    (
        90523,
        "CAD-GD",
        "FSCD-147",
        "MAE",
        10.35,
        "Text-only positive prompt (GroundingREC family), Table 1",
    ),
    (90523, "CAD-GD", "FSCD-147", "RMSE", 86.88, "Text-only positive prompt, Table 1"),
    (23597, "PseCo", "FSCD-147", "MAE", 16.58, "Text-only positive prompt, Table 1"),
    (23597, "PseCo", "FSCD-147", "RMSE", 129.77, "Text-only positive prompt, Table 1"),
    (
        23597,
        "PseCo",
        "FSCD-147",
        "AP",
        37.91,
        "Text-only positive prompt; published checkpoint, Table 1",
    ),
    (
        23597,
        "PseCo",
        "FSCD-147",
        "AP50",
        62.45,
        "Text-only positive prompt; published checkpoint, Table 1",
    ),
    (
        98352,
        "CountGD-Box",
        "FSCD-147",
        "MAE",
        15.01,
        "Text-only positive prompt, Table 1",
    ),
    (
        98352,
        "CountGD-Box",
        "FSCD-147",
        "RMSE",
        118.16,
        "Text-only positive prompt, Table 1",
    ),
    (
        98352,
        "CountGD-Box",
        "FSCD-147",
        "AP",
        30.44,
        "Text-only positive prompt, Table 1",
    ),
    (
        98352,
        "CountGD-Box",
        "FSCD-147",
        "AP50",
        61.56,
        "Text-only positive prompt, Table 1",
    ),
    # Table 2 — Blood Cell + OmniCount (positive text + internal exemplar)
    (
        34211,
        "CountGD",
        "Blood Cell Detection",
        "MAE",
        10.99,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        34211,
        "CountGD",
        "Blood Cell Detection",
        "RMSE",
        14.64,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        34211,
        "CountGD",
        "OmniCount (Fruits)",
        "MAE",
        2.76,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        34211,
        "CountGD",
        "OmniCount (Fruits)",
        "RMSE",
        3.11,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "Blood Cell Detection",
        "MAE",
        11.34,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "Blood Cell Detection",
        "RMSE",
        15.42,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "Blood Cell Detection",
        "AP",
        0.25,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "Blood Cell Detection",
        "AP50",
        0.45,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "OmniCount (Fruits)",
        "MAE",
        2.83,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "OmniCount (Fruits)",
        "RMSE",
        3.15,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "OmniCount (Fruits)",
        "AP",
        0.47,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    (
        98352,
        "CountGD-Box",
        "OmniCount (Fruits)",
        "AP50",
        0.61,
        "Positive text + 1 internal exemplar; no negatives, Table 2",
    ),
    # Table 4 — ShanghaiTech text only (+ pseudo-exemplars for CountGD++ only; baselines text only)
    (
        13620,
        "Grounding DINO",
        "ShanghaiTech Part A",
        "MAE",
        394.9,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        13620,
        "Grounding DINO",
        "ShanghaiTech Part A",
        "RMSE",
        537.5,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        13620,
        "Grounding DINO",
        "ShanghaiTech Part B",
        "MAE",
        58.3,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        13620,
        "Grounding DINO",
        "ShanghaiTech Part B",
        "RMSE",
        99.3,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        17526,
        "OWLv2",
        "ShanghaiTech Part A",
        "MAE",
        420.2,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        17526,
        "OWLv2",
        "ShanghaiTech Part A",
        "RMSE",
        553.3,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        17526,
        "OWLv2",
        "ShanghaiTech Part B",
        "MAE",
        81.5,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        17526,
        "OWLv2",
        "ShanghaiTech Part B",
        "RMSE",
        126.5,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98351,
        "CLIP-Count",
        "ShanghaiTech Part A",
        "MAE",
        192.6,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98351,
        "CLIP-Count",
        "ShanghaiTech Part A",
        "RMSE",
        308.4,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98351,
        "CLIP-Count",
        "ShanghaiTech Part B",
        "MAE",
        45.7,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98351,
        "CLIP-Count",
        "ShanghaiTech Part B",
        "RMSE",
        77.4,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98352,
        "CountGD-Box",
        "ShanghaiTech Part A",
        "MAE",
        132.2,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98352,
        "CountGD-Box",
        "ShanghaiTech Part A",
        "RMSE",
        253.9,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98352,
        "CountGD-Box",
        "ShanghaiTech Part B",
        "MAE",
        32.2,
        "Text-only positive prompt 'human', Table 4",
    ),
    (
        98352,
        "CountGD-Box",
        "ShanghaiTech Part B",
        "RMSE",
        57.9,
        "Text-only positive prompt 'human', Table 4",
    ),
    # Table 5 — VideoCount (Crystals)
    (
        98352,
        "CountVid",
        "VideoCount (Crystals)",
        "MAE",
        12.0,
        "Positive text + 3–8 manual internal exemplars per frame, Table 5",
    ),
    (
        98352,
        "CountVid",
        "VideoCount (Crystals)",
        "RMSE",
        13.5,
        "Positive text + 3–8 manual internal exemplars per frame, Table 5",
    ),
    (
        98352,
        "CountVid (text-only)",
        "VideoCount (Crystals)",
        "MAE",
        69.1,
        "Positive text only (no exemplars), Table 5",
    ),
    (
        98352,
        "CountVid (text-only)",
        "VideoCount (Crystals)",
        "RMSE",
        86.0,
        "Positive text only (no exemplars), Table 5",
    ),
    # Table A.1 — PairTally
    (
        34211,
        "CountGD",
        "PairTally",
        "MAE",
        46.67,
        "Positive text + 3 internal exemplars, Table A.1",
    ),
    (
        34211,
        "CountGD",
        "PairTally",
        "RMSE",
        70.85,
        "Positive text + 3 internal exemplars; reproduced by CountGD++ authors, Table A.1",
    ),
    (37428, "GeCo", "PairTally", "MAE", 50.24, "Exemplar-only (3 internal), Table A.1"),
    (98350, "DAVE", "PairTally", "MAE", 47.37, "Exemplar-only (3 internal), Table A.1"),
    (
        44599,
        "Qwen2.5-VL",
        "PairTally",
        "MAE",
        59.36,
        "Text-only positive prompt, Table A.1",
    ),
]

CLOSED_SOURCE_PAPER_IDS = {44599}


def resolve_dataset_ids(db) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, slug in DATASET.items():
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
    created = 0
    skipped = 0
    try:
        dataset_ids = resolve_dataset_ids(db)
        svc = EvaluationService(db)
        for paper_id, model_name, dataset_name, metric, score, note in ROWS:
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
            methodology = f"{note}. {SOURCE}."
            svc.create_evaluation(
                paper_id=paper_id,
                task_id=TASK_ID,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=methodology,
                metrics={metric: score},
                best_metric=metric,
                external_source_url="https://arxiv.org/abs/2512.23351",
                is_open=paper_id not in CLOSED_SOURCE_PAPER_IDS,
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
