#!/usr/bin/env python3
"""
Improve Depth Anything V2 evaluation results.

This script adds comprehensive evaluation results for Depth Anything V2
(ArXiv: 2406.09414) from Table 2 and Table 3 of the paper.

Table 2: Zero-shot relative depth estimation on 5 benchmarks
Table 3: Performance on DA-2K evaluation benchmark
"""

import sys
from typing import Dict, Optional
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.services.dataset_service import DatasetService
from backend.models.api import DatasetCreateRequest
from sqlalchemy.orm import Session

ARXIV_ID = "2406.09414"
TASK_ID = 16  # Depth estimation task ID

# Table 2: Zero-shot relative depth estimation
# Format: (dataset_id, dataset_name, model_name, metrics, best_metric)
TABLE_2_RESULTS = [
    # KITTI - ViT-S and ViT-B (ViT-G already exists)
    (
        75,
        "KITTI",
        "Depth Anything V2 (ViT-S)",
        {"AbsRel": "0.078", "delta1": "0.936"},
        "delta1",
    ),
    (
        75,
        "KITTI",
        "Depth Anything V2 (ViT-B)",
        {"AbsRel": "0.078", "delta1": "0.939"},
        "delta1",
    ),
    (
        75,
        "KITTI",
        "Depth Anything V2 (ViT-L)",
        {"AbsRel": "0.074", "delta1": "0.946"},
        "delta1",
    ),
    # NYUv2 - ViT-S and ViT-B (ViT-G already exists)
    (
        76,
        "NYUv2",
        "Depth Anything V2 (ViT-S)",
        {"AbsRel": "0.053", "delta1": "0.973"},
        "delta1",
    ),
    (
        76,
        "NYUv2",
        "Depth Anything V2 (ViT-B)",
        {"AbsRel": "0.049", "delta1": "0.976"},
        "delta1",
    ),
    (
        76,
        "NYUv2",
        "Depth Anything V2 (ViT-L)",
        {"AbsRel": "0.045", "delta1": "0.979"},
        "delta1",
    ),
    # Sintel - All models
    (
        None,
        "Sintel",
        "Depth Anything V2 (ViT-S)",
        {"AbsRel": "0.500", "delta1": "0.718"},
        "delta1",
    ),
    (
        None,
        "Sintel",
        "Depth Anything V2 (ViT-B)",
        {"AbsRel": "0.495", "delta1": "0.734"},
        "delta1",
    ),
    (
        None,
        "Sintel",
        "Depth Anything V2 (ViT-L)",
        {"AbsRel": "0.487", "delta1": "0.752"},
        "delta1",
    ),
    (
        None,
        "Sintel",
        "Depth Anything V2 (ViT-G)",
        {"AbsRel": "0.506", "delta1": "0.772"},
        "delta1",
    ),
    # ETH3D - All models
    (
        218,
        "ETH3D",
        "Depth Anything V2 (ViT-S)",
        {"AbsRel": "0.142", "delta1": "0.851"},
        "delta1",
    ),
    (
        218,
        "ETH3D",
        "Depth Anything V2 (ViT-B)",
        {"AbsRel": "0.137", "delta1": "0.858"},
        "delta1",
    ),
    (
        218,
        "ETH3D",
        "Depth Anything V2 (ViT-L)",
        {"AbsRel": "0.131", "delta1": "0.865"},
        "delta1",
    ),
    (
        218,
        "ETH3D",
        "Depth Anything V2 (ViT-G)",
        {"AbsRel": "0.132", "delta1": "0.862"},
        "delta1",
    ),
    # DIODE - All models
    (
        240,
        "DIODE",
        "Depth Anything V2 (ViT-S)",
        {"AbsRel": "0.073", "delta1": "0.942"},
        "delta1",
    ),
    (
        240,
        "DIODE",
        "Depth Anything V2 (ViT-B)",
        {"AbsRel": "0.068", "delta1": "0.950"},
        "delta1",
    ),
    (
        240,
        "DIODE",
        "Depth Anything V2 (ViT-L)",
        {"AbsRel": "0.066", "delta1": "0.952"},
        "delta1",
    ),
    (
        240,
        "DIODE",
        "Depth Anything V2 (ViT-G)",
        {"AbsRel": "0.065", "delta1": "0.954"},
        "delta1",
    ),
]

# Table 3: DA-2K evaluation benchmark
# Format: (dataset_id, dataset_name, model_name, metrics, best_metric)
TABLE_3_RESULTS = [
    (None, "DA-2K", "Depth Anything V2 (ViT-S)", {"Accuracy": "95.3"}, "Accuracy"),
    (None, "DA-2K", "Depth Anything V2 (ViT-B)", {"Accuracy": "97.0"}, "Accuracy"),
    (None, "DA-2K", "Depth Anything V2 (ViT-L)", {"Accuracy": "97.1"}, "Accuracy"),
    (None, "DA-2K", "Depth Anything V2 (ViT-G)", {"Accuracy": "97.4"}, "Accuracy"),
]


def get_paper_id(db: Session, arxiv_id: str) -> int:
    """Get paper ID by ArXiv ID."""
    print(f"Looking up paper with ArXiv ID: {arxiv_id}...")

    paper_service = PaperService(db)
    try:
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
        print(f"✓ Found paper: '{paper.title}' (ID={paper.id})")
        return int(paper.id)
    except Exception as e:
        print(f"✗ Error finding paper: {e}")
        raise


def get_or_create_sintel_dataset(db: Session, task_id: int) -> int:
    """Get or create Sintel dataset."""
    dataset_service = DatasetService(db)

    # Try to find existing dataset
    datasets_result = dataset_service.get_datasets(name="Sintel", page_size=10)
    if datasets_result.results:
        print(f"✓ Found existing Sintel dataset (ID={datasets_result.results[0].id})")
        return datasets_result.results[0].id

    # Create new dataset
    print("Creating Sintel dataset...")
    dataset_request = DatasetCreateRequest(
        name="Sintel",
        full_name="MPI Sintel Dataset",
        description="Synthetic dataset for optical flow and depth estimation from the open source 3D animated short film 'Sintel'",
        url="http://sintel.is.tue.mpg.de/",
        paper_url="https://link.springer.com/chapter/10.1007/978-3-642-33783-3_44",
        task_ids=[task_id],
    )

    dataset = dataset_service.create_dataset(dataset_request)
    print(f"✓ Created Sintel dataset (ID={dataset.id})")
    return dataset.id


def get_or_create_da2k_dataset(db: Session, task_id: int, paper_id: int) -> int:
    """Get or create DA-2K dataset."""
    dataset_service = DatasetService(db)

    # Try to find existing dataset
    datasets_result = dataset_service.get_datasets(name="DA-2K", page_size=10)
    if datasets_result.results:
        print(f"✓ Found existing DA-2K dataset (ID={datasets_result.results[0].id})")
        return datasets_result.results[0].id

    # Create new dataset
    print("Creating DA-2K dataset...")
    dataset_request = DatasetCreateRequest(
        name="DA-2K",
        full_name="Depth Anything 2K Evaluation Benchmark",
        description="Versatile evaluation benchmark for relative monocular depth estimation with ~1K high-resolution images and ~2K sparse pixel-pair relative-depth annotations across eight representative scenarios (indoor, outdoor, underwater, aerial, transparent/reflective objects, etc.)",
        url="https://depth-anything-v2.github.io",
        paper_url=f"https://arxiv.org/abs/{ARXIV_ID}",
        introduced_by_paper_id=paper_id,
        task_ids=[task_id],
    )

    dataset = dataset_service.create_dataset(dataset_request)
    print(f"✓ Created DA-2K dataset (ID={dataset.id})")
    return dataset.id


def check_existing_evaluation(
    db: Session, paper_id: int, task_id: int, dataset_id: int, model_name: str
) -> Optional[int]:
    """Check if evaluation already exists."""
    evaluation_service = EvaluationService(db)

    # Get all evaluations for this paper/task/dataset
    evaluations_result = evaluation_service.get_evaluations(
        paper_id=paper_id, task_id=task_id, dataset_id=dataset_id, page_size=100
    )

    # Check if model_name matches
    for eval_obj in evaluations_result.results:
        if eval_obj.model_name == model_name:
            return eval_obj.id

    return None


def add_evaluation(
    db: Session,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    dataset_name: str,
    model_name: str,
    metrics: Dict[str, str],
    best_metric: str,
) -> bool:
    """Add a single evaluation result."""
    evaluation_service = EvaluationService(db)

    # Check if already exists
    existing_id = check_existing_evaluation(
        db, paper_id, task_id, dataset_id, model_name
    )
    if existing_id:
        print(
            f"  ⊙ Evaluation already exists (ID={existing_id}): {model_name} on {dataset_name}"
        )
        return False

    try:
        evaluation = evaluation_service.create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            metrics=metrics,
            best_metric=best_metric,
            model_name=model_name,
        )
        print(
            f"  ✓ Added evaluation (ID={evaluation.id}): {model_name} on {dataset_name}"
        )
        print(f"    Metrics: {metrics}")
        return True
    except Exception as e:
        print(f"  ✗ Error adding evaluation: {e}")
        return False


def main():
    """Main function to add all evaluation results."""
    db = db_manager.session_local()
    try:
        # Get paper ID
        paper_id = get_paper_id(db, ARXIV_ID)
        print()

        # Get or create Sintel dataset
        sintel_id = get_or_create_sintel_dataset(db, TASK_ID)
        print()

        # Get or create DA-2K dataset
        da2k_id = get_or_create_da2k_dataset(db, TASK_ID, paper_id)
        print()

        # Process Table 2 results
        print("=" * 80)
        print("Adding Table 2: Zero-shot relative depth estimation results")
        print("=" * 80)

        added_count = 0
        skipped_count = 0

        for (
            dataset_id,
            dataset_name,
            model_name,
            metrics,
            best_metric,
        ) in TABLE_2_RESULTS:
            # Handle Sintel dataset ID
            if dataset_id is None and dataset_name == "Sintel":
                dataset_id = sintel_id

            if add_evaluation(
                db,
                paper_id,
                TASK_ID,
                dataset_id,
                dataset_name,
                model_name,
                metrics,
                best_metric,
            ):
                added_count += 1
            else:
                skipped_count += 1

        print()
        print(f"Table 2 Summary: {added_count} added, {skipped_count} skipped")
        print()

        # Process Table 3 results
        print("=" * 80)
        print("Adding Table 3: DA-2K evaluation benchmark results")
        print("=" * 80)

        table3_added = 0
        table3_skipped = 0

        for (
            dataset_id,
            dataset_name,
            model_name,
            metrics,
            best_metric,
        ) in TABLE_3_RESULTS:
            # Handle DA-2K dataset ID
            if dataset_id is None and dataset_name == "DA-2K":
                dataset_id = da2k_id

            if add_evaluation(
                db,
                paper_id,
                TASK_ID,
                dataset_id,
                dataset_name,
                model_name,
                metrics,
                best_metric,
            ):
                table3_added += 1
            else:
                table3_skipped += 1

        print()
        print(f"Table 3 Summary: {table3_added} added, {table3_skipped} skipped")
        print()

        # Final summary
        print("=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        print(f"Total evaluations added: {added_count + table3_added}")
        print(f"Total evaluations skipped: {skipped_count + table3_skipped}")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
