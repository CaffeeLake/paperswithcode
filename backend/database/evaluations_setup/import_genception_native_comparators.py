"""Import paper-native comparator evaluations for arXiv:2607.09024.

The candidates come from the GenCeption comparison table and the legacy PwC
dump, but every row below was verified in the evaluated model's own paper.
Comparison-only re-evaluations are intentionally excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_genception_native_comparators.py
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService

BASE_URL = "http://localhost:8000/api/v1"

EVALS = [
    {
        "arxiv_id": "2409.11355",
        "task_id": 417,
        "dataset_id": 670,
        "model_name": "Marigold + E2E FT",
        "metrics": {"mAE": "33.5"},
        "best_metric": "mAE",
        "is_open": True,
        "methodology": "Paper Table 2/6, Sintel DSINE protocol; mean angular error in degrees for the introduced end-to-end fine-tuned Marigold normal model.",
    },
    {
        "arxiv_id": "2504.11427",
        "task_id": 417,
        "dataset_id": 670,
        "model_name": "NormalCrafter",
        "metrics": {"mAE": "30.7"},
        "best_metric": "mAE",
        "is_open": True,
        "methodology": "Paper Table 1, Sintel consecutive-frame split from DSINE (1,064 frames); mean angular error in degrees.",
    },
    {
        "arxiv_id": "2512.01030",
        "task_id": 417,
        "dataset_id": 670,
        "model_name": "Lotus-2",
        "metrics": {"mAE": "30.3"},
        "best_metric": "mAE",
        "is_open": True,
        "methodology": "Paper Table II, zero-shot Sintel surface-normal estimation under the DSINE evaluation protocol; mean angular error in degrees.",
    },
    {
        "arxiv_id": "2507.15365",
        "task_id": 417,
        "dataset_id": 1180,
        "model_name": "DAViD Large",
        "metrics": {"mAE": "15.37"},
        "best_metric": "mAE",
        "num_parameters": 340_000_000,
        "is_open": True,
        "methodology": "Paper Table 2, Hi4D surface-normal estimation; Large single-task model, mean angular error in degrees.",
    },
    {
        "arxiv_id": "2507.15365",
        "task_id": 16,
        "dataset_id": 1178,
        "model_name": "DAViD Large",
        "metrics": {"AbsRel": "0.012"},
        "best_metric": "AbsRel",
        "num_parameters": 340_000_000,
        "is_open": True,
        "methodology": "Paper Table 1, Goliath relative-depth evaluation; Large single-task model, best introduced AbsRel.",
    },
    {
        "arxiv_id": "2507.15365",
        "task_id": 337,
        "dataset_id": 1181,
        "model_name": "DAViD Large",
        "metrics": {"MSE": "0.0009"},
        "best_metric": "MSE",
        "num_parameters": 340_000_000,
        "is_open": True,
        "methodology": "Paper Table 3, PhotoMatte85 soft foreground segmentation; Large single-task model MSE.",
    },
    {
        "arxiv_id": "2408.12569",
        "task_id": 417,
        "dataset_id": 1180,
        "model_name": "Sapiens 2B",
        "metrics": {"mAE": "12.14"},
        "best_metric": "mAE",
        "num_parameters": 2_160_000_000,
        "is_open": True,
        "methodology": "Paper Table 6, Hi4D surface-normal estimation; mean angular error in degrees for Sapiens-2B.",
    },
    {
        "arxiv_id": "2512.08924",
        "task_id": 418,
        "dataset_id": 670,
        "model_name": "D4RT",
        "metrics": {"ATE": "0.065", "RPE-T": "0.024", "RPE-R": "0.126"},
        "best_metric": "ATE",
        "is_open": False,
        "methodology": "Paper Table 6, Sintel camera-pose estimation; ATE, relative pose translation error, and relative pose rotation error from the introduced D4RT model.",
    },
    {
        "arxiv_id": "2201.00487",
        "task_id": 419,
        "dataset_id": 1182,
        "model_name": "ReferFormer Video-Swin-B",
        "metrics": {"J&F": "61.1"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 1, Ref-DAVIS17 validation set; standard J&F for ReferFormer with Video-Swin-B.",
    },
    {
        "arxiv_id": "2407.11325",
        "task_id": 419,
        "dataset_id": 1182,
        "model_name": "VISA Chat-UniVi-13B",
        "metrics": {"J&F": "70.4"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 2, Ref-DAVIS17; best introduced VISA variant using Chat-UniVi-13B.",
    },
    {
        "arxiv_id": "2407.11325",
        "task_id": 419,
        "dataset_id": 1183,
        "model_name": "VISA Chat-UniVi-13B",
        "metrics": {"J&F": "44.5"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 2, MeViS; best introduced VISA variant using Chat-UniVi-13B.",
    },
    {
        "arxiv_id": "2508.21809",
        "task_id": 419,
        "dataset_id": 1182,
        "model_name": "VoCap",
        "metrics": {"J&F": "75.1"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 5, zero-shot RefVOS-DAVIS validation evaluation; standard J&F for VoCap.",
    },
    {
        "arxiv_id": "2508.21809",
        "task_id": 419,
        "dataset_id": 1183,
        "model_name": "VoCap + FindTrack",
        "metrics": {"J&F": "53.0"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 5, MeViS; best introduced VoCap setup, combined with FindTrack, under the standard J&F metric.",
    },
    {
        "arxiv_id": "2410.23287",
        "task_id": 419,
        "dataset_id": 1182,
        "model_name": "REM Wan-14B",
        "metrics": {"J&F": "75.0"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 1, Ref-DAVIS validation set; best introduced REM variant with the Wan-14B video diffusion backbone.",
    },
    {
        "arxiv_id": "2410.23287",
        "task_id": 419,
        "dataset_id": 1183,
        "model_name": "REM Wan-14B",
        "metrics": {"J&F": "60.3"},
        "best_metric": "J&F",
        "is_open": True,
        "methodology": "Paper Table 2, official MeViS evaluation; best introduced REM Wan-14B setup trained with the paper's full segmentation data mix.",
    },
    {
        "arxiv_id": "2409.06662",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "GVHMR",
        "metrics": {"MPJPE": "72.6"},
        "best_metric": "MPJPE",
        "is_open": True,
        "methodology": "Paper main comparison table, EMDB subset 2; MPJPE in millimeters for the introduced GVHMR model with bounding-box input and flip evaluation.",
    },
    {
        "arxiv_id": "2403.17346",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "TRAM",
        "metrics": {"MPJPE": "74.4"},
        "best_metric": "MPJPE",
        "is_open": True,
        "methodology": "Paper Table 4, EMDB subset 2; MPJPE in millimeters for TRAM's VIMO body-motion estimator.",
    },
    {
        "arxiv_id": "2505.01425",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "GENMO",
        "metrics": {"MPJPE": "73.0"},
        "best_metric": "MPJPE",
        "is_open": False,
        "methodology": "Paper Table 2, EMDB subset 2; MPJPE in millimeters for the introduced full GENMO model.",
    },
    {
        "arxiv_id": "2312.07531",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "WHAM ViT",
        "metrics": {"MPJPE": "79.7"},
        "best_metric": "MPJPE",
        "is_open": True,
        "methodology": "Paper Table 1, EMDB subset 2; MPJPE in millimeters for the best introduced WHAM ViT variant.",
    },
    {
        "arxiv_id": "2412.14444",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "GenHMR",
        "metrics": {"MPJPE": "88.2"},
        "best_metric": "MPJPE",
        "is_open": False,
        "methodology": "Paper Table 1, EMDB; MPJPE in millimeters for the introduced GenHMR model using five UGS refinement iterations.",
    },
    {
        "arxiv_id": "2501.07800",
        "task_id": 295,
        "dataset_id": 1179,
        "model_name": "MQ-HMR",
        "metrics": {"MPJPE": "92.5"},
        "best_metric": "MPJPE",
        "is_open": False,
        "methodology": "Paper Table 1, EMDB; MPJPE in millimeters for BioPose's introduced MQ-HMR component with ViT-H and 96 pose tokens.",
    },
]


async def ensure_paper(db, arxiv_id: str) -> Paper:
    paper = (
        db.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .first()
    )
    if paper is not None:
        return paper

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )
    paper_id = PaperService(db).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Could not reload imported paper {arxiv_id}")
    return paper


def validate_leaderboard(db, spec: dict) -> None:
    row = (
        db.execute(
            text(
                """
            SELECT td.supports_harness, array_agg(m.name) AS metrics
            FROM task_datasets td
            JOIN task_dataset_metrics tdm
              ON (tdm.task_id, tdm.dataset_id) = (td.task_id, td.dataset_id)
            JOIN metrics m ON m.id = tdm.metric_id
            WHERE td.task_id = :task_id AND td.dataset_id = :dataset_id
            GROUP BY td.supports_harness
            """
            ),
            spec,
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["supports_harness"]:
        raise RuntimeError(
            f"Invalid leaderboard for {spec['task_id']}/{spec['dataset_id']}"
        )
    allowed = set(row["metrics"])
    if spec["best_metric"] not in allowed or not set(spec["metrics"]) <= allowed:
        raise RuntimeError(
            f"Metrics {spec['metrics']} are not allowed for "
            f"{spec['task_id']}/{spec['dataset_id']}: {sorted(allowed)}"
        )


def post_evaluation(token: str, payload: dict) -> int:
    request = urllib.request.Request(
        f"{BASE_URL}/evaluations/",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return int(json.load(response)["id"])
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Evaluation API failed ({exc.code}): {exc.read().decode()}"
        ) from exc


async def main() -> None:
    token = os.environ["PWC_ADMIN_API_TOKEN"]
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper_ids: dict[str, int] = {}
        for arxiv_id in dict.fromkeys(spec["arxiv_id"] for spec in EVALS):
            paper = await ensure_paper(db, arxiv_id)
            paper_ids[arxiv_id] = int(paper.id)

        created = 0
        unchanged = 0
        for spec in EVALS:
            validate_leaderboard(db, spec)
            paper_id = paper_ids[spec["arxiv_id"]]
            db.execute(
                text(
                    """
                    INSERT INTO paper_tasks (paper_id, task_id, source)
                    VALUES (:paper_id, :task_id, 'manual')
                    ON CONFLICT (paper_id, task_id) DO NOTHING
                    """
                ),
                {"paper_id": paper_id, "task_id": spec["task_id"]},
            )
            db.commit()

            existing_id = db.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id = :paper_id AND task_id = :task_id
                      AND dataset_id = :dataset_id AND model_name = :model_name
                      AND harness IS NULL AND best_metric = :best_metric
                    """
                ),
                {**spec, "paper_id": paper_id},
            ).scalar_one_or_none()
            if existing_id is not None:
                print("unchanged", existing_id, spec["arxiv_id"], spec["model_name"])
                unchanged += 1
                continue

            payload = {
                key: value for key, value in spec.items() if key not in {"arxiv_id"}
            }
            payload["paper_id"] = paper_id
            payload["source_url"] = (
                f"https://paperswithcode.co/paper/{spec['arxiv_id']}"
            )
            evaluation_id = post_evaluation(token, payload)
            print("created", evaluation_id, spec["arxiv_id"], spec["model_name"])
            created += 1
        print(f"summary created={created} unchanged={unchanged}")
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    asyncio.run(main())
