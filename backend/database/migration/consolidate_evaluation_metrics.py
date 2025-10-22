"""
Consolidate evaluation metrics by merging duplicate rows.

This script consolidates evaluation rows that represent the same model evaluation
but have metrics split across multiple rows. It merges the metrics JSONB fields
and keeps the row with the most complete metadata.
"""

import logging
from typing import Dict, List, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def calculate_completeness_score(evaluation: DBEvaluation) -> int:
    """Calculate completeness score for an evaluation row."""
    score = 0

    # Count non-null fields
    if evaluation.methodology:
        score += 2
    if evaluation.evaluated_on:
        score += 2
    if evaluation.external_source_url:
        score += 1
    if evaluation.best_rank is not None:
        score += 3
    if evaluation.uses_additional_data is not None:
        score += 1

    # Count number of metrics
    if evaluation.metrics:
        score += len(evaluation.metrics)

    return score


def select_best_row(evaluations: List[DBEvaluation]) -> DBEvaluation:
    """
    Select the best row from a group of duplicates based on completeness.

    Criteria (in order):
    1. Most complete data (non-null fields)
    2. Most metrics
    3. Newer created_at
    """
    if len(evaluations) == 1:
        return evaluations[0]

    # Score each evaluation
    scored = [(calculate_completeness_score(e), e.created_at, e) for e in evaluations]

    # Sort by score (desc), then created_at (desc)
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    return scored[0][2]


def merge_metrics(evaluations: List[DBEvaluation]) -> Dict[str, Any]:
    """
    Merge metrics from multiple evaluation rows.

    If the same metric appears with different values, prefer the value
    from the row with the highest completeness score.
    """
    merged = {}

    # Sort evaluations by completeness score (descending)
    sorted_evals = sorted(
        evaluations,
        key=lambda e: (calculate_completeness_score(e), e.created_at),
        reverse=True,
    )

    # Merge metrics, with priority to earlier (more complete) evaluations
    for evaluation in reversed(sorted_evals):
        if evaluation.metrics:
            merged.update(evaluation.metrics)

    return merged


def consolidate_duplicates(db: Session, dry_run: bool = False) -> Dict:
    """
    Consolidate duplicate evaluation rows.

    Args:
        db: Database session
        dry_run: If True, only log actions without making changes

    Returns:
        Statistics dictionary
    """
    logger.info("=" * 80)
    logger.info("CONSOLIDATING EVALUATION DUPLICATES")
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    logger.info("=" * 80)

    # Find duplicate groups
    query = text("""
        SELECT
            paper_id,
            task_id,
            dataset_id,
            model_name,
            ARRAY_AGG(id ORDER BY created_at DESC) as eval_ids
        FROM evaluations
        GROUP BY paper_id, task_id, dataset_id, model_name
        HAVING COUNT(*) > 1
        ORDER BY model_name
    """)

    result = db.execute(query)
    duplicate_groups = result.fetchall()

    logger.info(f"\nFound {len(duplicate_groups)} duplicate groups to consolidate")

    stats = {
        "groups_processed": 0,
        "rows_deleted": 0,
        "rows_updated": 0,
        "metrics_merged": 0,
    }

    for paper_id, task_id, dataset_id, model_name, eval_ids in duplicate_groups:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing: {model_name}")
        logger.info(
            f"Paper ID: {paper_id}, Task ID: {task_id}, Dataset ID: {dataset_id}"
        )
        logger.info(f"Evaluation IDs: {eval_ids}")

        # Fetch all evaluations in this group
        evaluations = db.query(DBEvaluation).filter(DBEvaluation.id.in_(eval_ids)).all()

        logger.info(f"Found {len(evaluations)} duplicate rows")

        # Show current metrics
        for eval in evaluations:
            logger.info(
                f"  ID {eval.id}: metrics={eval.metrics}, completeness={calculate_completeness_score(eval)}"
            )

        # Select the best row to keep
        best_row = select_best_row(evaluations)
        logger.info(
            f"\n→ Selected row ID {best_row.id} as primary (completeness score: {calculate_completeness_score(best_row)})"
        )

        # Merge all metrics
        merged_metrics = merge_metrics(evaluations)
        logger.info(f"→ Merged metrics: {merged_metrics}")

        if not dry_run:
            # Update the best row with merged metrics
            best_row.metrics = merged_metrics
            db.add(best_row)

            # Delete other rows
            rows_to_delete = [e for e in evaluations if e.id != best_row.id]
            for eval in rows_to_delete:
                logger.info(f"  Deleting row ID {eval.id}")
                db.delete(eval)

            db.commit()

            stats["rows_deleted"] += len(rows_to_delete)
            stats["rows_updated"] += 1
        else:
            logger.info(f"  [DRY RUN] Would delete {len(evaluations) - 1} rows")
            logger.info(f"  [DRY RUN] Would update row ID {best_row.id}")

        stats["groups_processed"] += 1
        stats["metrics_merged"] += len(merged_metrics)

    return stats


def verify_consolidation(db: Session):
    """Verify that consolidation was successful."""
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION")
    logger.info("=" * 80)

    # Check for remaining duplicates
    query = text("""
        SELECT COUNT(*) as duplicate_groups
        FROM (
            SELECT paper_id, task_id, dataset_id, model_name
            FROM evaluations
            GROUP BY paper_id, task_id, dataset_id, model_name
            HAVING COUNT(*) > 1
        ) as dups
    """)

    result = db.execute(query)
    remaining_duplicates = result.scalar()

    if remaining_duplicates == 0:
        logger.info("✅ No duplicate groups remaining")
    else:
        logger.warning(f"⚠️  {remaining_duplicates} duplicate groups still exist")

    # Count total evaluations
    total_count = db.query(DBEvaluation).count()
    logger.info(f"Total evaluations: {total_count}")

    # Check backup
    try:
        backup_count = db.execute(
            text("SELECT COUNT(*) FROM evaluations_backup")
        ).scalar()
        logger.info(f"Backup table: {backup_count} rows")
    except Exception as e:
        logger.warning(f"Could not verify backup: {e}")

    return remaining_duplicates == 0


def main():
    """Main function to consolidate evaluation duplicates."""
    import sys

    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv

    session = db_manager.session_local()

    try:
        # Run consolidation
        stats = consolidate_duplicates(session, dry_run=dry_run)

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("CONSOLIDATION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Groups processed: {stats['groups_processed']}")
        logger.info(f"Rows updated: {stats['rows_updated']}")
        logger.info(f"Rows deleted: {stats['rows_deleted']}")
        logger.info(f"Total metrics merged: {stats['metrics_merged']}")
        logger.info("=" * 80)

        if not dry_run:
            # Verify consolidation
            success = verify_consolidation(session)

            if success:
                logger.info("\n✅ Consolidation completed successfully!")
            else:
                logger.warning("\n⚠️  Consolidation completed but duplicates remain")
        else:
            logger.info("\n[DRY RUN] No changes were made")

    except Exception as e:
        logger.error(f"Error during consolidation: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
