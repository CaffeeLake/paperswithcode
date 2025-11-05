"""
Remove the generic COCO dataset from the database.

This script safely removes the base COCO dataset entry, which is too generic
and should be replaced with specific COCO variants like "COCO test-dev",
"COCO 2014 val", etc.

The script will:
1. Find the COCO dataset
2. Check for evaluations, task associations, paper associations
3. Check for child datasets (datasets with COCO as parent)
4. Remove all relationships
5. Delete the COCO dataset

Usage:
    uv run --env-file backend/keys.env python backend/database/datasets_setup/remove_coco_dataset.py [--dry-run]
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


def find_coco_dataset(db) -> Optional[DBDataset]:
    """Find the base COCO dataset (not variants)."""
    # Look for COCO datasets that don't have a parent (base datasets)
    # Match "COCO" exactly or as part of the name, but not variants like "COCO test-dev"
    from sqlalchemy import and_, or_

    coco_datasets = (
        db.query(DBDataset)
        .filter(
            and_(
                or_(
                    DBDataset.name.ilike("COCO"),
                    DBDataset.name.ilike("COCO (%"),
                    DBDataset.name.ilike("MS COCO"),
                ),
                DBDataset.parent_dataset_id.is_(None),
                # Exclude variants that have variant_type or split_name set
                and_(
                    DBDataset.variant_type.is_(None),
                    DBDataset.split_name.is_(None),
                ),
            )
        )
        .all()
    )

    if not coco_datasets:
        # Try without parent filter, but still exclude variants
        coco_datasets = (
            db.query(DBDataset)
            .filter(
                or_(
                    DBDataset.name.ilike("COCO"),
                    DBDataset.name.ilike("COCO (%"),
                    DBDataset.name.ilike("MS COCO"),
                ),
                # Exclude variants - both variant_type and split_name should be None
                and_(
                    DBDataset.variant_type.is_(None),
                    DBDataset.split_name.is_(None),
                ),
            )
            .all()
        )

    if len(coco_datasets) > 1:
        logger.warning(
            f"Found {len(coco_datasets)} COCO datasets. Will need to handle each:"
        )
        for ds in coco_datasets:
            logger.warning(
                f"  - ID {ds.id}: {ds.name} (parent_id={ds.parent_dataset_id})"
            )
        # Prioritize exact match "COCO"
        exact_match = [ds for ds in coco_datasets if ds.name == "COCO"]
        if exact_match:
            return exact_match[0]

    return coco_datasets[0] if coco_datasets else None


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


def remove_coco_dataset(dry_run: bool = True):
    """Remove the COCO dataset and all its relationships."""
    db = db_manager.session_local()
    try:
        # Find COCO dataset
        coco = find_coco_dataset(db)

        if not coco:
            logger.error("COCO dataset not found in database")
            return False

        logger.info(f"Found COCO dataset: ID {coco.id}, name: '{coco.name}'")

        # Get statistics
        stats = get_dataset_stats(db, coco.id)
        logger.info("Current statistics:")
        logger.info(f"  - Evaluations: {stats['evaluations']}")
        logger.info(f"  - Task associations: {stats['task_associations']}")
        logger.info(f"  - Paper associations: {stats['paper_associations']}")
        logger.info(f"  - Child datasets: {stats['child_datasets']}")
        logger.info(f"  - Leaderboard metrics: {stats['leaderboard_metrics']}")

        # Check for child datasets
        child_datasets = (
            db.query(DBDataset).filter(DBDataset.parent_dataset_id == coco.id).all()
        )

        if child_datasets:
            logger.warning(
                f"Found {len(child_datasets)} child datasets with COCO as parent:"
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
            logger.info(f"  - COCO dataset (ID {coco.id})")
            logger.info(
                f"  - {len(child_datasets)} child datasets would have parent_dataset_id set to NULL"
            )
            logger.info("\nRun without --dry-run to actually perform the deletion")
            return True

        # Actually perform the deletion
        logger.info("\n=== DELETING COCO DATASET ===")

        # Delete evaluations
        if stats["evaluations"] > 0:
            evaluations = (
                db.query(DBEvaluation).filter(DBEvaluation.dataset_id == coco.id).all()
            )
            for eval_obj in evaluations:
                db.delete(eval_obj)
            logger.info(f"Deleted {stats['evaluations']} evaluations")

        # Delete task associations
        if stats["task_associations"] > 0:
            task_assocs = (
                db.query(TaskDataset).filter(TaskDataset.dataset_id == coco.id).all()
            )
            for assoc in task_assocs:
                db.delete(assoc)
            logger.info(f"Deleted {stats['task_associations']} task associations")

        # Delete paper associations
        if stats["paper_associations"] > 0:
            paper_assocs = (
                db.query(PaperDataset).filter(PaperDataset.dataset_id == coco.id).all()
            )
            for assoc in paper_assocs:
                db.delete(assoc)
            logger.info(f"Deleted {stats['paper_associations']} paper associations")

        # Delete leaderboard metric links (task-dataset-metric triples)
        if stats["leaderboard_metrics"] > 0:
            leaderboard_metrics = (
                db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.dataset_id == coco.id)
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

        # Finally, delete the COCO dataset itself
        db.delete(coco)
        logger.info(f"Deleted COCO dataset (ID {coco.id})")

        # Commit all changes
        db.commit()
        logger.info("\n✓ Successfully removed COCO dataset and all relationships")

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
        success = remove_coco_dataset(dry_run=dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Failed to remove COCO dataset: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
