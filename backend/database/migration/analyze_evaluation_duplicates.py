"""
Analyze evaluation duplicates to understand consolidation requirements.

This script identifies evaluation rows that should be consolidated because they
represent the same model evaluation but split metrics across multiple rows.
"""

import logging
from typing import Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def analyze_duplicates(db: Session) -> Dict:
    """Analyze evaluation duplicates and return statistics."""

    logger.info("=" * 80)
    logger.info("EVALUATION DUPLICATE ANALYSIS")
    logger.info("=" * 80)

    # Get total count
    total_evaluations = db.query(DBEvaluation).count()
    logger.info(f"\nTotal evaluations in database: {total_evaluations}")

    # Find groups with multiple rows (duplicates)
    # Group by: paper_id, task_id, dataset_id, model_name
    query = text("""
        SELECT
            paper_id,
            task_id,
            dataset_id,
            model_name,
            COUNT(*) as row_count,
            ARRAY_AGG(id ORDER BY created_at DESC) as eval_ids,
            ARRAY_AGG(metrics::text ORDER BY created_at DESC) as all_metrics
        FROM evaluations
        GROUP BY paper_id, task_id, dataset_id, model_name
        HAVING COUNT(*) > 1
        ORDER BY row_count DESC, model_name
    """)

    result = db.execute(query)
    duplicates = result.fetchall()

    logger.info(f"\nDuplicate groups found: {len(duplicates)}")

    if len(duplicates) == 0:
        logger.info("\n✅ No duplicates found! Database is already consolidated.")
        return {
            "total_evaluations": total_evaluations,
            "duplicate_groups": 0,
            "rows_to_consolidate": 0,
            "rows_after_consolidation": total_evaluations,
        }

    # Calculate statistics
    total_duplicate_rows = sum(dup[4] for dup in duplicates)
    rows_after_consolidation = total_evaluations - (
        total_duplicate_rows - len(duplicates)
    )

    logger.info(f"Total duplicate rows: {total_duplicate_rows}")
    logger.info(f"Rows will be reduced by: {total_duplicate_rows - len(duplicates)}")
    logger.info(f"Evaluations after consolidation: {rows_after_consolidation}")

    # Show top 10 duplicate groups
    logger.info("\n" + "=" * 80)
    logger.info("TOP DUPLICATE GROUPS (by row count)")
    logger.info("=" * 80)

    for i, dup in enumerate(duplicates[:10], 1):
        paper_id, task_id, dataset_id, model_name, row_count, eval_ids, all_metrics = (
            dup
        )

        logger.info(f"\n{i}. Model: {model_name}")
        logger.info(
            f"   Paper ID: {paper_id}, Task ID: {task_id}, Dataset ID: {dataset_id}"
        )
        logger.info(f"   Duplicate rows: {row_count}")
        logger.info(f"   Evaluation IDs: {eval_ids}")

        # Parse and show metrics from each row
        for j, metrics_str in enumerate(all_metrics, 1):
            # Parse the string representation of JSONB
            logger.info(f"   Row {j} metrics: {metrics_str}")

    # Analyze by dataset
    logger.info("\n" + "=" * 80)
    logger.info("DUPLICATES BY DATASET")
    logger.info("=" * 80)

    dataset_query = text("""
        SELECT
            d.name as dataset_name,
            COUNT(DISTINCT CONCAT(e.paper_id, '-', e.task_id, '-', e.dataset_id, '-', e.model_name)) as duplicate_groups,
            COUNT(*) as total_rows
        FROM evaluations e
        JOIN datasets d ON e.dataset_id = d.id
        WHERE (e.paper_id, e.task_id, e.dataset_id, e.model_name) IN (
            SELECT paper_id, task_id, dataset_id, model_name
            FROM evaluations
            GROUP BY paper_id, task_id, dataset_id, model_name
            HAVING COUNT(*) > 1
        )
        GROUP BY d.name
        ORDER BY duplicate_groups DESC
    """)

    dataset_result = db.execute(dataset_query)
    dataset_stats = dataset_result.fetchall()

    for dataset_name, dup_groups, total_rows in dataset_stats:
        logger.info(
            f"{dataset_name}: {dup_groups} duplicate groups ({total_rows} rows)"
        )

    return {
        "total_evaluations": total_evaluations,
        "duplicate_groups": len(duplicates),
        "rows_to_consolidate": total_duplicate_rows,
        "rows_after_consolidation": rows_after_consolidation,
        "duplicates": duplicates,
    }


def create_backup(db: Session):
    """Create a backup of the evaluations table."""
    logger.info("\n" + "=" * 80)
    logger.info("CREATING BACKUP")
    logger.info("=" * 80)

    try:
        # Drop backup table if it exists
        db.execute(text("DROP TABLE IF EXISTS evaluations_backup"))
        db.commit()

        # Create backup table
        db.execute(
            text("""
            CREATE TABLE evaluations_backup AS
            SELECT * FROM evaluations
        """)
        )
        db.commit()

        # Get backup count
        backup_count = db.execute(
            text("SELECT COUNT(*) FROM evaluations_backup")
        ).scalar()
        logger.info(f"✅ Backup created: evaluations_backup ({backup_count} rows)")

        return True
    except Exception as e:
        logger.error(f"❌ Failed to create backup: {e}")
        db.rollback()
        return False


def main():
    """Main function to analyze duplicates and create backup."""
    session = db_manager.session_local()

    try:
        # Analyze duplicates
        stats = analyze_duplicates(session)

        # Create backup
        if stats["duplicate_groups"] > 0:
            logger.info(
                "\n⚠️  Duplicates found. Creating backup before consolidation..."
            )
            if create_backup(session):
                logger.info("\n✅ Analysis complete. Ready for consolidation.")
            else:
                logger.error("\n❌ Backup failed. Do not proceed with consolidation.")
        else:
            logger.info("\n✅ No duplicates found. No consolidation needed.")

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total evaluations: {stats['total_evaluations']}")
        logger.info(f"Duplicate groups: {stats['duplicate_groups']}")
        logger.info(f"Rows to consolidate: {stats['rows_to_consolidate']}")
        logger.info(f"After consolidation: {stats['rows_after_consolidation']}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
