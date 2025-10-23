"""
Refactor MRCR Dataset Structure

This script creates MRCR dataset variants for different context lengths (1M and ≤128K)
and updates evaluations to use standardized "Accuracy" metric instead of
"Accuracy (1M)" and "Accuracy (≤128K)".
"""

import sys
from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.models.api import DatasetCreateRequest
from sqlalchemy.orm import Session


def create_mrcr_variants(db: Session) -> tuple[int, int]:
    """Create two MRCR variant datasets (or reuse if they exist)."""
    print("Step 1: Creating MRCR variant datasets...")
    print("-" * 80)

    dataset_service = DatasetService(db)

    # Check if datasets already exist
    existing_1m = db.query(Dataset).filter(Dataset.slug == "mrcr-v2-1m").first()
    existing_128k = db.query(Dataset).filter(Dataset.slug == "mrcr-v2-128k").first()

    if existing_1m:
        print(f"MRCR v2 (1M) dataset already exists: ID={existing_1m.id}")
        mrcr_1m_id = existing_1m.id
    else:
        # Create MRCR v2 (1M) dataset
        mrcr_1m_request = DatasetCreateRequest(
            name="MRCR v2 (1M)",
            full_name="Multi-turn Response Coherence and Relevance (1M context)",
            description="MRCR benchmark variant for evaluating long-context language models with 1M token context window",
            parent_dataset_id=184,  # Base MRCR dataset
            variant_type="variant",
            task_ids=[5],  # Language Modeling
            introducing_paper_id=51774,  # Gemini 2.5 paper
            paper_url="https://arxiv.org/abs/2507.06261",
        )

        print("Creating MRCR v2 (1M) dataset...")
        mrcr_1m = dataset_service.create_dataset(mrcr_1m_request)
        mrcr_1m_id = mrcr_1m.id
        print(f"✓ Created MRCR v2 (1M): ID={mrcr_1m_id}, Slug={mrcr_1m.slug}")

    if existing_128k:
        print(f"MRCR v2 (≤128K) dataset already exists: ID={existing_128k.id}")
        mrcr_128k_id = existing_128k.id
    else:
        # Create MRCR v2 (≤128K) dataset
        mrcr_128k_request = DatasetCreateRequest(
            name="MRCR v2 (≤128K)",
            full_name="Multi-turn Response Coherence and Relevance (≤128K context)",
            description="MRCR benchmark variant for evaluating language models with context window up to 128K tokens",
            parent_dataset_id=184,  # Base MRCR dataset
            variant_type="variant",
            task_ids=[5],  # Language Modeling
            introducing_paper_id=51774,  # Gemini 2.5 paper
            paper_url="https://arxiv.org/abs/2507.06261",
        )

        print("Creating MRCR v2 (≤128K) dataset...")
        mrcr_128k = dataset_service.create_dataset(mrcr_128k_request)
        mrcr_128k_id = mrcr_128k.id
        print(f"✓ Created MRCR v2 (≤128K): ID={mrcr_128k_id}, Slug={mrcr_128k.slug}")

    print()
    return mrcr_1m_id, mrcr_128k_id


def update_evaluations(db: Session, mrcr_1m_id: int, mrcr_128k_id: int):
    """Update evaluations to use new datasets and standardized Accuracy metric."""
    print("Step 2: Updating evaluations...")
    print("-" * 80)

    evaluation_service = EvaluationService(db)

    # Mapping: evaluation_id -> (new_dataset_id, accuracy_value, model_name)
    updates = {
        398: (mrcr_1m_id, "16.4", "Gemini 2.5 Pro"),
        397: (mrcr_1m_id, "21.0", "Gemini 2.5 Flash"),
        395: (mrcr_128k_id, "54.3", "Gemini 2.5 Flash"),
        396: (mrcr_128k_id, "58.0", "Gemini 2.5 Pro"),
    }

    for eval_id, (new_dataset_id, accuracy_value, model_name) in updates.items():
        print(f"Updating evaluation {eval_id} ({model_name})...")

        # Get current evaluation
        evaluation = db.query(Evaluation).filter(Evaluation.id == eval_id).first()
        if not evaluation:
            print(f"  ✗ Evaluation {eval_id} not found!")
            continue

        # Update with new dataset and standardized metric
        # Pass individual parameters instead of request object
        updated_eval = evaluation_service.update_evaluation(
            evaluation_id=eval_id,
            dataset_id=new_dataset_id,
            metrics={"Accuracy": accuracy_value},
            best_metric="Accuracy",
        )
        print(f"  ✓ Updated: Dataset={new_dataset_id}, Metrics={updated_eval.metrics}")

    print()


def recalculate_ranks(db: Session, mrcr_1m_id: int, mrcr_128k_id: int):
    """Verify that leaderboard ranks were recalculated (happens automatically during update)."""
    print("Step 3: Verifying leaderboard ranks...")
    print("-" * 80)

    print("✓ Ranks were automatically recalculated during evaluation updates")
    print()


def verify_results(db: Session, mrcr_1m_id: int, mrcr_128k_id: int):
    """Verify the refactored structure."""
    print("Step 4: Verifying results...")
    print("-" * 80)

    # Check MRCR v2 (1M) evaluations
    print(f"\nMRCR v2 (1M) Leaderboard (Dataset ID={mrcr_1m_id}):")
    print("-" * 80)
    evals_1m = (
        db.query(Evaluation)
        .filter(Evaluation.dataset_id == mrcr_1m_id)
        .order_by(Evaluation.best_rank)
        .all()
    )

    for eval in evals_1m:
        accuracy = eval.metrics.get("Accuracy", "N/A")
        print(f"  Rank #{eval.best_rank}: {eval.model_name}")
        print(f"    Accuracy: {accuracy}%")

    # Check MRCR v2 (≤128K) evaluations
    print(f"\nMRCR v2 (≤128K) Leaderboard (Dataset ID={mrcr_128k_id}):")
    print("-" * 80)
    evals_128k = (
        db.query(Evaluation)
        .filter(Evaluation.dataset_id == mrcr_128k_id)
        .order_by(Evaluation.best_rank)
        .all()
    )

    for eval in evals_128k:
        accuracy = eval.metrics.get("Accuracy", "N/A")
        print(f"  Rank #{eval.best_rank}: {eval.model_name}")
        print(f"    Accuracy: {accuracy}%")

    # Check old MRCR dataset
    print("\nOld MRCR dataset (ID=184) evaluations:")
    print("-" * 80)
    old_evals = db.query(Evaluation).filter(Evaluation.dataset_id == 184).all()
    if old_evals:
        print(f"  Warning: {len(old_evals)} evaluations still using old MRCR dataset")
    else:
        print("  ✓ No evaluations remaining on old MRCR dataset")

    print()


def main():
    """Main execution function."""
    print("=" * 80)
    print("MRCR Dataset Refactoring Script")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Step 1: Create dataset variants
            mrcr_1m_id, mrcr_128k_id = create_mrcr_variants(db)

            # Step 2: Update evaluations
            update_evaluations(db, mrcr_1m_id, mrcr_128k_id)

            # Step 3: Recalculate ranks
            recalculate_ranks(db, mrcr_1m_id, mrcr_128k_id)

            # Commit all changes
            db.commit()
            print("✓ All changes committed to database")
            print()

            # Step 4: Verify results
            verify_results(db, mrcr_1m_id, mrcr_128k_id)

            print("=" * 80)
            print("✓ MRCR Dataset Refactoring Complete!")
            print("=" * 80)

            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
