"""
Link COCO dataset to Object Detection task in the task_datasets junction table.

This script adds the relationship between:
- COCO (Common Objects in Context) dataset (ID: 1)
- Object Detection task (ID: 2)

This allows the frontend to display COCO as a benchmark dataset for the Object Detection task.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.database.connection import DatabaseManager
from backend.models.database import (
    TaskDataset as DBTaskDataset,
    Task as DBTask,
    Dataset as DBDataset,
)
from sqlalchemy import and_

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()


def link_dataset_to_task(task_name: str, dataset_name: str):
    """Link a dataset to a task in the task_datasets table."""
    session = db_manager.session_local()

    try:
        # Find the task
        task = session.query(DBTask).filter(DBTask.name == task_name).first()
        if not task:
            logger.error(f"Task '{task_name}' not found in database")
            return False

        logger.info(f"Found task: {task.name} (ID: {task.id})")

        # Find the dataset
        dataset = (
            session.query(DBDataset)
            .filter(DBDataset.name.ilike(f"%{dataset_name}%"))
            .first()
        )
        if not dataset:
            logger.error(f"Dataset containing '{dataset_name}' not found in database")
            return False

        logger.info(f"Found dataset: {dataset.name} (ID: {dataset.id})")

        # Check if the relationship already exists
        existing = (
            session.query(DBTaskDataset)
            .filter(
                and_(
                    DBTaskDataset.task_id == task.id,
                    DBTaskDataset.dataset_id == dataset.id,
                )
            )
            .first()
        )

        if existing:
            logger.info(
                f"Relationship already exists between '{task.name}' and '{dataset.name}'"
            )
            return True

        # Create the relationship
        task_dataset = DBTaskDataset(task_id=task.id, dataset_id=dataset.id)
        session.add(task_dataset)
        session.commit()

        logger.info(f"✅ Successfully linked '{dataset.name}' to '{task.name}' task")
        return True

    except Exception as e:
        logger.error(f"Error linking dataset to task: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def main():
    """Main function to link COCO to Object Detection."""
    logger.info("=" * 60)
    logger.info("Linking COCO Dataset to Object Detection Task")
    logger.info("=" * 60)

    success = link_dataset_to_task("Object Detection", "COCO")

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("✅ COCO dataset successfully linked to Object Detection task!")
        logger.info("=" * 60)
        logger.info("\nYou can now:")
        logger.info("1. Visit http://167.235.148.241:8080/tasks/object-detection")
        logger.info("2. Click on the 'Leaderboards' tab")
        logger.info("3. See the COCO dataset benchmark results")
    else:
        logger.error("\n❌ Failed to link COCO dataset to Object Detection task")
        sys.exit(1)


if __name__ == "__main__":
    main()
