"""
Remove the SatLidar (SatLidar1M) dataset from the database.

This script safely removes the SatLidar dataset, which is an internal Meta dataset
and not useful for building public leaderboards.

The script will:
1. Find the SatLidar dataset
2. Check for evaluations, task associations, paper associations
3. Check for child datasets
4. Remove all relationships
5. Delete the SatLidar dataset

Usage:
    uv run --env-file backend/keys.env python scripts/remove_satlidar_dataset.py [--dry-run]
"""

import sys
import logging
from typing import Optional

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    TaskDataset,
    PaperDataset,
    TaskDatasetMetric,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATASET_ID = 258  # SatLidar dataset ID


def find_satlidar_dataset(db) -> Optional[DBDataset]:
    """Find the SatLidar dataset."""
    dataset = db.query(DBDataset).filter(DBDataset.id == DATASET_ID).first()
    return dataset


def get_dataset_stats(db, dataset_id: int) -> dict:
    """Get statistics about what's linked to this dataset."""
    stats = {
        "evaluations": db.query(DBEvaluation)
        .filter(DBEvaluation.dataset_id == dataset_id)
        .count(),
        "task_associations": db.query(TaskDataset)
        .filter(TaskDataset.dataset_id == dataset_id)
        .count(),
        "paper_associations": db.query(PaperDataset)
        .filter(PaperDataset.dataset_id == dataset_id)
        .count(),
        "child_datasets": db.query(DBDataset)
        .filter(DBDataset.parent_dataset_id == dataset_id)
        .count(),
        "leaderboard_metrics": db.query(TaskDatasetMetric)
        .filter(TaskDatasetMetric.dataset_id == dataset_id)
        .count(),
    }
    return stats


def remove_satlidar_dataset(dry_run: bool = True):
    """Remove the SatLidar dataset and all its relationships."""
    db = db_manager.session_local()
    try:
        # Find SatLidar dataset
        satlidar = find_satlidar_dataset(db)

        if not satlidar:
            logger.error(f"SatLidar dataset (ID {DATASET_ID}) not found in database")
            return False

        logger.info(
            f"Found SatLidar dataset: ID {satlidar.id}, name: '{satlidar.name}'"
        )

        # Get statistics
        stats = get_dataset_stats(db, satlidar.id)
        logger.info("Current statistics:")
        logger.info(f"  - Evaluations: {stats['evaluations']}")
        logger.info(f"  - Task associations: {stats['task_associations']}")
        logger.info(f"  - Paper associations: {stats['paper_associations']}")
        logger.info(f"  - Child datasets: {stats['child_datasets']}")
        logger.info(f"  - Leaderboard metrics: {stats['leaderboard_metrics']}")

        # Check for child datasets
        child_datasets = (
            db.query(DBDataset).filter(DBDataset.parent_dataset_id == satlidar.id).all()
        )

        if child_datasets:
            logger.warning(
                f"Found {len(child_datasets)} child datasets with SatLidar as parent:"
            )
            for child in child_datasets:
                logger.warning(
                    f"  - ID {child.id}: {child.name} (variant_type: {child.variant_type}, split_name: {child.split_name})"
                )
            logger.warning(
                "Child datasets will have their parent_dataset_id set to NULL (cascade behavior)"
            )

        if dry_run:
            logger.info("\n=== DRY RUN MODE ===")
            logger.info("Would delete:")
            logger.info(f"  - {stats['evaluations']} evaluations")
            logger.info(f"  - {stats['task_associations']} task associations")
            logger.info(f"  - {stats['paper_associations']} paper associations")
            logger.info(f"  - {stats['leaderboard_metrics']} leaderboard metric links")
            logger.info(f"  - SatLidar dataset (ID {satlidar.id})")
            if child_datasets:
                logger.info(
                    f"  - {len(child_datasets)} child datasets would have parent_dataset_id set to NULL"
                )
            logger.info("\nRun without --dry-run to actually perform the deletion")
            return True

        # Actually perform the deletion
        logger.info("\n=== DELETING SATLIDAR DATASET ===")

        # Delete evaluations
        if stats["evaluations"] > 0:
            evaluations = (
                db.query(DBEvaluation)
                .filter(DBEvaluation.dataset_id == satlidar.id)
                .all()
            )
            for eval_obj in evaluations:
                logger.info(
                    f"  Deleting evaluation ID {eval_obj.id} (Model: {eval_obj.model_name}, Metrics: {eval_obj.metrics})"
                )
                db.delete(eval_obj)
            logger.info(f"Deleted {stats['evaluations']} evaluations")

        # Delete task associations
        if stats["task_associations"] > 0:
            task_assocs = (
                db.query(TaskDataset)
                .filter(TaskDataset.dataset_id == satlidar.id)
                .all()
            )
            for assoc in task_assocs:
                db.delete(assoc)
            logger.info(f"Deleted {stats['task_associations']} task associations")

        # Delete paper associations
        if stats["paper_associations"] > 0:
            paper_assocs = (
                db.query(PaperDataset)
                .filter(PaperDataset.dataset_id == satlidar.id)
                .all()
            )
            for assoc in paper_assocs:
                db.delete(assoc)
            logger.info(f"Deleted {stats['paper_associations']} paper associations")

        # Delete leaderboard metric links (task-dataset-metric triples)
        if stats["leaderboard_metrics"] > 0:
            leaderboard_metrics = (
                db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.dataset_id == satlidar.id)
                .all()
            )
            for lm in leaderboard_metrics:
                db.delete(lm)
            logger.info(
                f"Deleted {stats['leaderboard_metrics']} leaderboard metric links"
            )

        # Update child datasets (set parent_dataset_id to NULL)
        # This happens automatically due to ON DELETE SET NULL, but let's be explicit
        if child_datasets:
            for child in child_datasets:
                child.parent_dataset_id = None
            logger.info(
                f"Set parent_dataset_id to NULL for {len(child_datasets)} child datasets"
            )

        # Finally, delete the SatLidar dataset itself
        db.delete(satlidar)
        logger.info(f"Deleted SatLidar dataset (ID {satlidar.id})")

        # Commit all changes
        db.commit()
        logger.info("\n✓ Successfully removed SatLidar dataset and all relationships")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error during deletion: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv

    if dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    try:
        success = remove_satlidar_dataset(dry_run=dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Failed to remove SatLidar dataset: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
