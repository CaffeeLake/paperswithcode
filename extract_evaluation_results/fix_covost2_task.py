"""
Fix CoVost2 dataset task association and evaluation.

CoVost2 should be linked to Automatic Speech Recognition (task_id=12), not Audio-Language Models (task_id=10).
"""

import sys
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    TaskDataset,
    Task as DBTask,
    Evaluation as DBEvaluation,
)


def fix_covost2_task_association():
    """Fix CoVost2 dataset to be linked to Automatic Speech Recognition instead of Audio-Language Models."""
    session: Session = db_manager.session_local()

    try:
        # Find CoVost2 dataset (ID: 256 from step_4.json)
        dataset = session.query(DBDataset).filter(DBDataset.id == 256).first()
        if not dataset:
            print("❌ Dataset with ID 256 not found")
            return False

        print(f"Found dataset: {dataset.name} (ID: {dataset.id})")

        # Get task IDs
        asr_task = session.query(DBTask).filter(DBTask.id == 12).first()
        audio_lang_task = session.query(DBTask).filter(DBTask.id == 10).first()

        if not asr_task:
            print("❌ Automatic Speech Recognition task (ID: 12) not found")
            return False

        if not audio_lang_task:
            print("❌ Audio-Language Models task (ID: 10) not found")
            return False

        print(f"ASR Task: {asr_task.name} (ID: {asr_task.id})")
        print(f"Audio-Lang Task: {audio_lang_task.name} (ID: {audio_lang_task.id})")

        # Check current task associations
        current_links = (
            session.query(TaskDataset).filter(TaskDataset.dataset_id == 256).all()
        )
        current_task_ids = [link.task_id for link in current_links]
        print(f"Current task associations: {current_task_ids}")

        # Remove Audio-Language Models association (task_id=10)
        audio_lang_link = (
            session.query(TaskDataset)
            .filter(TaskDataset.dataset_id == 256, TaskDataset.task_id == 10)
            .first()
        )

        if audio_lang_link:
            session.delete(audio_lang_link)
            print("✓ Removed association with Audio-Language Models (task_id=10)")
        else:
            print("⚠ No existing association with Audio-Language Models found")

        # Ensure Automatic Speech Recognition association (task_id=12)
        asr_link = (
            session.query(TaskDataset)
            .filter(TaskDataset.dataset_id == 256, TaskDataset.task_id == 12)
            .first()
        )

        if not asr_link:
            asr_link = TaskDataset(task_id=12, dataset_id=256)
            session.add(asr_link)
            print("✓ Added association with Automatic Speech Recognition (task_id=12)")
        else:
            print("✓ Association with Automatic Speech Recognition already exists")

        session.commit()

        # Verify final state
        final_links = (
            session.query(TaskDataset).filter(TaskDataset.dataset_id == 256).all()
        )
        final_task_ids = [link.task_id for link in final_links]
        print(f"Final task associations: {final_task_ids}")

        return True

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        return False
    finally:
        session.close()


def fix_covost2_evaluation():
    """Update the CoVost2 evaluation to use Automatic Speech Recognition (task_id=12) instead of Audio-Language Models (task_id=10)."""
    session: Session = db_manager.session_local()

    try:
        # Find the evaluation (ID: 551 from the output)
        evaluation = session.query(DBEvaluation).filter(DBEvaluation.id == 551).first()
        if not evaluation:
            print("❌ Evaluation with ID 551 not found")
            return False

        print(
            f"Found evaluation: ID={evaluation.id}, paper_id={evaluation.paper_id}, task_id={evaluation.task_id}, dataset_id={evaluation.dataset_id}"
        )

        if evaluation.task_id != 10:
            print(
                f"⚠ Evaluation already has task_id={evaluation.task_id}, not 10. Skipping update."
            )
            return True

        # Update task_id to 12 (Automatic Speech Recognition)
        evaluation.task_id = 12
        session.commit()

        print(
            f"✓ Updated evaluation ID {evaluation.id} to use task_id=12 (Automatic Speech Recognition)"
        )

        # Recalculate ranks for this leaderboard
        from backend.services.evaluation_service import EvaluationService

        eval_service = EvaluationService(session)
        eval_service.recalculate_ranks(task_id=12, dataset_id=256)
        session.commit()

        print("✓ Recalculated ranks for task_id=12, dataset_id=256")

        return True

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        return False
    finally:
        session.close()


def main():
    print("=" * 60)
    print("Fixing CoVost2 task association")
    print("=" * 60)

    # Fix dataset-task association
    print("\n1. Fixing dataset-task association...")
    success1 = fix_covost2_task_association()

    # Fix evaluation
    print("\n2. Fixing evaluation...")
    success2 = fix_covost2_evaluation()

    if success1 and success2:
        print("\n" + "=" * 60)
        print("✅ All fixes completed successfully!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ Some fixes failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
