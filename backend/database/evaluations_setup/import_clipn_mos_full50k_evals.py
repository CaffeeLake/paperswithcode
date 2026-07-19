"""Restore CLIPN paper-native results on the MOS/MCM full-50K boards.

This intentionally imports only the six requested CLIPN-A ViT-B/16 cells
from Table 1 of arXiv:2308.12213.  The Textures cells already exist, and the
table's comparator, ViT-B/32, and average rows are out of scope.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_clipn_mos_full50k_evals.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

PAPER_ID = 19698
ARXIV_ID = "2308.12213"
TASK_ID = 317
MODEL_NAME = "CLIPN-A ViT-B/16 (zero-shot)"
SOURCE_URL = f"https://arxiv.org/abs/{ARXIV_ID}"
EXPECTED_METRICS = {"AUROC", "FPR95"}


@dataclass(frozen=True)
class EvalSpec:
    dataset_id: int
    dataset_label: str
    ood_subset: str
    metric: str
    score: str


EVALS = (
    EvalSpec(
        dataset_id=1222,
        dataset_label="SUN",
        ood_subset="the MOS-curated 10,000-image SUN subset from 50 classes",
        metric="AUROC",
        score="93.93",
    ),
    EvalSpec(
        dataset_id=1222,
        dataset_label="SUN",
        ood_subset="the MOS-curated 10,000-image SUN subset from 50 classes",
        metric="FPR95",
        score="26.17",
    ),
    EvalSpec(
        dataset_id=1223,
        dataset_label="iNaturalist",
        ood_subset=(
            "the MOS-curated 10,000-image iNaturalist subset from 110 plant "
            "classes absent from ImageNet-1K"
        ),
        metric="AUROC",
        score="95.27",
    ),
    EvalSpec(
        dataset_id=1223,
        dataset_label="iNaturalist",
        ood_subset=(
            "the MOS-curated 10,000-image iNaturalist subset from 110 plant "
            "classes absent from ImageNet-1K"
        ),
        metric="FPR95",
        score="23.94",
    ),
    EvalSpec(
        dataset_id=1224,
        dataset_label="Places",
        ood_subset="the MOS-curated 10,000-image Places subset from 50 classes",
        metric="AUROC",
        score="92.28",
    ),
    EvalSpec(
        dataset_id=1224,
        dataset_label="Places",
        ood_subset="the MOS-curated 10,000-image Places subset from 50 classes",
        metric="FPR95",
        score="33.45",
    ),
)


def _methodology(spec: EvalSpec) -> str:
    direction = "higher" if spec.metric == "AUROC" else "lower"
    return (
        f"CLIPN paper Table 1 large-scale zero-shot OOD detection result for "
        f"{spec.dataset_label}, using the original MOS/MCM full-50K protocol: "
        f"all 50,000 ILSVRC2012 ImageNet-1K validation images are ID and "
        f"{spec.ood_subset} is OOD. CLIPN-A uses the agreeing-to-differ "
        f"threshold-free inference algorithm with learnable 'no' prompts and "
        f"an OpenCLIP ViT-B/16 image encoder. CLIPN was pretrained on CC3M "
        f"for 10 epochs with batch size 2,048; the underlying CLIP was "
        f"pretrained on LAION-2B. Reported {spec.metric} in percent ({direction} "
        f"is better), averaged over three independent runs. Source: paper "
        f"Table 1."
    )


def _validate_scope(db) -> None:
    paper = (
        db.execute(
            text(
                """
            SELECT id, arxiv_id, date_published
            FROM papers
            WHERE id = :paper_id AND is_latest_version
            """
            ),
            {"paper_id": PAPER_ID},
        )
        .mappings()
        .one_or_none()
    )
    if paper is None or paper["arxiv_id"] != ARXIV_ID:
        raise RuntimeError(f"Paper {PAPER_ID} is not latest arXiv:{ARXIV_ID}")
    if paper["date_published"] is None:
        raise RuntimeError(f"Paper {PAPER_ID} is missing date_published")

    rows = (
        db.execute(
            text(
                """
            SELECT d.id, d.name, d.description, d.split_name,
                   td.supports_harness,
                   array_agg(m.name ORDER BY m.name) AS metrics
            FROM datasets d
            JOIN task_datasets td
              ON td.dataset_id = d.id AND td.task_id = :task_id
            JOIN task_dataset_metrics tdm
              ON tdm.dataset_id = td.dataset_id AND tdm.task_id = td.task_id
            JOIN metrics m ON m.id = tdm.metric_id
            WHERE d.id = ANY(:dataset_ids)
            GROUP BY d.id, d.name, d.description, d.split_name,
                     td.supports_harness
            """
            ),
            {
                "task_id": TASK_ID,
                "dataset_ids": sorted({spec.dataset_id for spec in EVALS}),
            },
        )
        .mappings()
        .all()
    )
    by_id = {int(row["id"]): row for row in rows}
    expected_ids = {1222, 1223, 1224}
    if set(by_id) != expected_ids:
        raise RuntimeError(
            f"Expected configured datasets {sorted(expected_ids)}, got {sorted(by_id)}"
        )

    for dataset_id, row in by_id.items():
        if row["supports_harness"]:
            raise RuntimeError(f"Dataset {dataset_id} unexpectedly supports harness")
        if set(row["metrics"]) != EXPECTED_METRICS:
            raise RuntimeError(
                f"Dataset {dataset_id} metrics are {row['metrics']}, "
                f"expected {sorted(EXPECTED_METRICS)}"
            )
        protocol_text = " ".join(
            filter(None, (row["name"], row["description"], row["split_name"]))
        ).lower()
        if "50,000" not in protocol_text and "50k" not in protocol_text:
            raise RuntimeError(
                f"Dataset {dataset_id} does not identify the full-50K ID protocol"
            )


def _upsert_eval(
    db,
    service: EvaluationService,
    spec: EvalSpec,
) -> tuple[str, int]:
    params = {
        "paper_id": PAPER_ID,
        "task_id": TASK_ID,
        "dataset_id": spec.dataset_id,
        "model_name": MODEL_NAME,
        "best_metric": spec.metric,
    }
    existing = (
        db.execute(
            text(
                """
            SELECT id, metrics, methodology, uses_additional_data, is_open,
                   source_url, external_source_url, harness,
                   num_parameters, hf_model_url
            FROM evaluations
            WHERE paper_id = :paper_id
              AND task_id = :task_id
              AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND harness IS NULL
              AND best_metric = :best_metric
            """
            ),
            params,
        )
        .mappings()
        .one_or_none()
    )

    metrics = {spec.metric: spec.score}
    methodology = _methodology(spec)
    if existing is None:
        created = service.create_evaluation(
            paper_id=PAPER_ID,
            task_id=TASK_ID,
            dataset_id=spec.dataset_id,
            model_name=MODEL_NAME,
            methodology=methodology,
            metrics=metrics,
            uses_additional_data=True,
            is_open=True,
            best_metric=spec.metric,
            source_url=SOURCE_URL,
            num_parameters=None,
            hf_model_url=None,
        )
        return "created", int(created.id)

    desired = {
        "metrics": metrics,
        "methodology": methodology,
        "uses_additional_data": True,
        "is_open": True,
        "source_url": SOURCE_URL,
        "external_source_url": SOURCE_URL,
        "harness": None,
        "num_parameters": None,
        "hf_model_url": None,
    }
    if {key: existing[key] for key in desired} == desired:
        return "unchanged", int(existing["id"])

    db.execute(
        text(
            """
            UPDATE evaluations
            SET metrics = CAST(:metrics AS jsonb),
                methodology = :methodology,
                uses_additional_data = TRUE,
                is_open = TRUE,
                source_url = :source_url,
                external_source_url = :source_url,
                external = FALSE,
                harness = NULL,
                num_parameters = NULL,
                hf_model_url = NULL,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "id": existing["id"],
            "metrics": json.dumps(metrics),
            "methodology": methodology,
            "source_url": SOURCE_URL,
        },
    )
    db.commit()
    return "updated", int(existing["id"])


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        _validate_scope(db)
        service = EvaluationService(db)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        affected: list[tuple[int, str]] = []

        for spec in EVALS:
            status, evaluation_id = _upsert_eval(db, service, spec)
            counts[status] += 1
            affected.append((spec.dataset_id, spec.metric))
            print(
                status,
                f"evaluation_id={evaluation_id}",
                f"dataset_id={spec.dataset_id}",
                f"metric={spec.metric}",
                f"score={spec.score}",
            )

        for dataset_id, metric in sorted(set(affected)):
            service.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)

        print(
            "skipped dataset_id=1226 label=Textures "
            "reason=paper-native CLIPN-A rows already exist"
        )
        print("skipped comparator, ViT-B/32, and average rows by requested scope")
        print("summary", counts)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
