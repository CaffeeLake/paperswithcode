"""
Add PICABench Evaluation Results

This script adds evaluation results for various models evaluated on PICABench
from Table 1 of the paper (arxiv: 2510.17681).

The results show overall accuracy scores for each model on the PICABench benchmark.
"""

import sys
from typing import Dict
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.services.dataset_service import DatasetService
from sqlalchemy.orm import Session

# PICABench evaluation results from Table 1 (Overall Accuracy column)
MODEL_RESULTS = [
    {"model_name": "Gemini", "accuracy": "59.87"},
    {"model_name": "GPT-Image-1", "accuracy": "61.08"},
    {"model_name": "Seedream 4.0", "accuracy": "61.91"},
    {"model_name": "DiMOO", "accuracy": "35.66"},
    {"model_name": "Uniworld-V1", "accuracy": "37.68"},
    {"model_name": "Bagel", "accuracy": "45.07"},
    {"model_name": "Bagel-Think", "accuracy": "46.48"},
    {"model_name": "OmniGen2", "accuracy": "46.79"},
    {"model_name": "Hidream-E1.1", "accuracy": "47.90"},
    {"model_name": "Step1X-Edit", "accuracy": "48.23"},
    {"model_name": "Qwen-Image-Edit", "accuracy": "58.29"},
    {"model_name": "Flux.1 Kontext", "accuracy": "48.93"},
    {"model_name": "Flux.1 Kontext+SFT", "accuracy": "50.64"},
]

ARXIV_ID = "2510.17681"
DATASET_ID = 146  # PICABench dataset ID
TASK_ID = 18  # Image Editing task ID


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


def verify_dataset(db: Session, dataset_id: int) -> bool:
    """Verify dataset exists and get its name."""
    print(f"Verifying dataset ID: {dataset_id}...")

    dataset_service = DatasetService(db)
    try:
        dataset = dataset_service.get_dataset(dataset_id)
        if dataset:
            print(f"✓ Found dataset: '{dataset.name}' (ID={dataset.id})")
            return True
        else:
            print(f"✗ Dataset ID {dataset_id} not found")
            return False
    except Exception as e:
        print(f"✗ Error finding dataset: {e}")
        return False


def create_evaluation(
    db: Session,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_result: Dict[str, str],
) -> bool:
    """
    Create an evaluation entry for a model result.

    Returns:
        True if successful, False otherwise
    """
    try:
        evaluation_service = EvaluationService(db)

        metrics = {"Accuracy": model_result["accuracy"]}

        evaluation = evaluation_service.create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=model_result["model_name"],
            metrics=metrics,
            best_metric="Accuracy",
        )

        print(f"  ✓ Created evaluation ID: {evaluation.id}")
        return True
    except Exception as e:
        print(f"  ✗ Error creating evaluation: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main execution function."""
    print("=" * 80)
    print("Add PICABench Evaluation Results")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Step 1: Get paper ID
            print("Step 1: Looking up PICABench paper...")
            print("-" * 80)
            paper_id = get_paper_id(db, ARXIV_ID)
            print()

            # Step 2: Verify dataset
            print("Step 2: Verifying dataset...")
            print("-" * 80)
            if not verify_dataset(db, DATASET_ID):
                print("✗ Dataset verification failed. Exiting.")
                return 1
            print()

            # Step 3: Process model results
            print("Step 3: Processing model evaluation results...")
            print("-" * 80)
            print(f"Total models to process: {len(MODEL_RESULTS)}")
            print()

            created_evaluations = []
            failed_evaluations = []

            for i, model_result in enumerate(MODEL_RESULTS, 1):
                model_name = model_result["model_name"]
                accuracy = model_result["accuracy"]

                print(f"[{i}/{len(MODEL_RESULTS)}] {model_name}: {accuracy}%")

                # Create evaluation
                if create_evaluation(db, paper_id, TASK_ID, DATASET_ID, model_result):
                    created_evaluations.append(
                        {
                            "model": model_name,
                            "accuracy": accuracy,
                        }
                    )
                else:
                    failed_evaluations.append(
                        {"model": model_name, "reason": "Creation failed"}
                    )

                print()

            # Commit all changes
            print("Step 4: Committing changes to database...")
            print("-" * 80)
            db.commit()
            print("✓ All changes committed successfully")
            print()

            # Step 5: Generate summary report
            print("=" * 80)
            print("SUMMARY REPORT")
            print("=" * 80)
            print()

            print(f"Total models processed: {len(MODEL_RESULTS)}")
            print(f"Evaluations created successfully: {len(created_evaluations)}")
            print(f"Failed evaluations: {len(failed_evaluations)}")
            print()

            if created_evaluations:
                print("✓ Successfully Created Evaluations:")
                print("-" * 80)
                for eval_info in created_evaluations:
                    print(f"  • {eval_info['model']}: {eval_info['accuracy']}%")
                print()

            if failed_evaluations:
                print("⚠ Failed Evaluations:")
                print("-" * 80)
                for fail_info in failed_evaluations:
                    print(f"  • {fail_info['model']}: {fail_info['reason']}")
                print()

            print("=" * 80)
            print("✓ Script completed successfully!")
            print("=" * 80)

            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
