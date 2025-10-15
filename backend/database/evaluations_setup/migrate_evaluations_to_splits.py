"""
Migrate existing evaluations to the correct dataset splits.

This script finds evaluations that are linked to parent datasets (like COCO)
when they should be linked to specific splits (like COCO test-dev, COCO minival).

It uses the legacy evaluation-tables.json to find the correct split for each evaluation.

Usage:
    uv run --env-file backend/keys.env backend/database/evaluations_setup/migrate_evaluations_to_splits.py
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict

import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "host": os.getenv("PWC_DB_HOST", "localhost"),
        "port": os.getenv("PWC_DB_PORT", "5432"),
        "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("PWC_DB_USER", "postgres"),
        "password": os.getenv("PWC_DB_PASSWORD", ""),
    }
    return psycopg2.connect(**db_params)


def find_dataset_split(
    cursor, parent_dataset_id: int, dataset_name: str
) -> Optional[int]:
    """
    Find the correct dataset split ID based on the dataset name from legacy data.

    Args:
        cursor: Database cursor
        parent_dataset_id: ID of the parent dataset (e.g., COCO)
        dataset_name: Name from legacy data (e.g., "COCO test-dev", "COCO minival")

    Returns:
        Dataset split ID or None
    """
    dataset_name_lower = dataset_name.lower()

    # Map common split patterns
    split_keywords = {
        "test-dev": ["test-dev", "testdev", "test dev"],
        "test-challenge": ["test-challenge", "test challenge"],
        "minival": ["minival", "mini val", "mini-val"],
        "val2017": ["val2017", "val 2017", "2017 val"],
        "val": [
            "2014 val",
            "2017 val",
        ],  # Specific patterns to avoid matching "minival"
        "test": [" test", "test "],
    }

    # Try to identify the split
    for split_name, patterns in split_keywords.items():
        for pattern in patterns:
            if pattern in dataset_name_lower:
                # Look for a split with this split_name under the parent
                cursor.execute(
                    """
                    SELECT id, name, split_name
                    FROM datasets
                    WHERE parent_dataset_id = %s
                        AND variant_type = 'split'
                        AND split_name = %s
                    LIMIT 1
                """,
                    (parent_dataset_id, split_name),
                )

                split = cursor.fetchone()
                if split:
                    logger.debug(
                        f"Matched '{dataset_name}' to split '{split['name']}' "
                        f"(ID: {split['id']}, split_name: {split['split_name']})"
                    )
                    return split["id"]

    # If no specific split found, check if the evaluation is actually for the parent
    # (e.g., just "MS COCO" or "COCO" without a split)
    if (
        "test" not in dataset_name_lower
        and "val" not in dataset_name_lower
        and "train" not in dataset_name_lower
    ):
        logger.debug(
            f"No split pattern found in '{dataset_name}', using parent dataset"
        )
        return parent_dataset_id

    logger.warning(f"Could not find split for dataset name: '{dataset_name}'")
    return None


def load_evaluation_dataset_mappings(eval_tables_file: Path) -> Dict[int, str]:
    """
    Load mappings from paper ArXiv IDs to their dataset names from evaluation tables.

    Returns:
        Dictionary mapping {paper_arxiv_id: dataset_name}
    """
    logger.info(f"Loading evaluation tables from {eval_tables_file}")

    with open(eval_tables_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = {}

    # Process each task
    for task_item in data:
        # Process each dataset under this task
        for dataset in task_item.get("datasets", []):
            dataset_name = dataset.get("dataset", "")

            # Process each evaluation row
            if "sota" in dataset and "rows" in dataset["sota"]:
                for row in dataset["sota"]["rows"]:
                    paper_url = row.get("paper_url", "")

                    # Extract ArXiv ID
                    if "arxiv.org/abs/" in paper_url:
                        arxiv_id = paper_url.split("/")[-1].split("v")[0]

                        # Store mapping (paper could have multiple evaluations, but we'll use the most common)
                        if arxiv_id:
                            mappings[arxiv_id] = dataset_name

    logger.info(
        f"Loaded {len(mappings)} paper-to-dataset mappings from evaluation tables"
    )
    return mappings


def migrate_evaluations(
    cursor, paper_dataset_mappings: Dict[str, str], dry_run: bool = True
):
    """
    Migrate evaluations from parent datasets to correct splits.

    Args:
        cursor: Database cursor
        paper_dataset_mappings: Mapping from ArXiv ID to dataset name
        dry_run: If True, don't actually update the database
    """
    # Find all evaluations linked to parent COCO dataset
    cursor.execute("""
        SELECT
            e.id as eval_id,
            e.model_name,
            e.paper_id,
            e.dataset_id,
            p.arxiv_id,
            p.title as paper_title,
            d.name as dataset_name,
            d.parent_dataset_id
        FROM evaluations e
        JOIN papers p ON e.paper_id = p.id
        JOIN datasets d ON e.dataset_id = d.id
        WHERE d.name = 'COCO'
            AND d.parent_dataset_id IS NULL
            AND p.is_latest_version = TRUE
        ORDER BY e.id
    """)

    evaluations = cursor.fetchall()

    logger.info(f"Found {len(evaluations)} evaluations linked to parent COCO dataset")

    if not evaluations:
        logger.info("No evaluations to migrate")
        return

    migrated_count = 0
    skipped_count = 0

    for eval_row in evaluations:
        eval_id = eval_row["eval_id"]
        arxiv_id = eval_row["arxiv_id"]
        current_dataset_id = eval_row["dataset_id"]
        model_name = eval_row["model_name"]

        # Look up the dataset name from legacy data
        legacy_dataset_name = paper_dataset_mappings.get(arxiv_id)

        if not legacy_dataset_name:
            logger.warning(
                f"Evaluation {eval_id}: No legacy dataset mapping found for paper {arxiv_id}"
            )
            skipped_count += 1
            continue

        # Find the correct split
        correct_split_id = find_dataset_split(
            cursor, current_dataset_id, legacy_dataset_name
        )

        if not correct_split_id or correct_split_id == current_dataset_id:
            logger.debug(
                f"Evaluation {eval_id}: Already on correct dataset or no split needed"
            )
            skipped_count += 1
            continue

        # Get the split name
        cursor.execute("SELECT name FROM datasets WHERE id = %s", (correct_split_id,))
        split_info = cursor.fetchone()

        logger.info(
            f"Evaluation {eval_id} ({model_name[:50]}...): "
            f"Migrating from COCO (ID: {current_dataset_id}) to "
            f"{split_info['name']} (ID: {correct_split_id})"
        )

        if not dry_run:
            # Update the evaluation
            cursor.execute(
                """
                UPDATE evaluations
                SET dataset_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """,
                (correct_split_id, eval_id),
            )

        migrated_count += 1

    logger.info("\n" + "=" * 80)
    logger.info("Migration Summary")
    logger.info("=" * 80)
    logger.info(f"Total evaluations checked: {len(evaluations)}")
    logger.info(f"Migrated to splits: {migrated_count}")
    logger.info(f"Skipped (no change needed): {skipped_count}")
    logger.info(f"Dry run mode: {dry_run}")
    logger.info("=" * 80)


def main():
    """Main function to migrate evaluations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate evaluations to dataset splits"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes without confirmation"
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Migrating Evaluations to Dataset Splits")
    logger.info("=" * 80)

    # Path to evaluation tables
    eval_tables_file = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "legacy_pwc_data"
        / "evaluation-tables.json"
    )

    if not eval_tables_file.exists():
        logger.error(f"Evaluation tables file not found: {eval_tables_file}")
        return 1

    # Load paper-dataset mappings
    paper_dataset_mappings = load_evaluation_dataset_mappings(eval_tables_file)

    # Connect to database
    logger.info("Connecting to database...")
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Run migration in dry-run mode first
        logger.info("\n" + "=" * 80)
        logger.info("DRY RUN - No changes will be made")
        logger.info("=" * 80 + "\n")
        migrate_evaluations(cursor, paper_dataset_mappings, dry_run=True)

        # Check if we should apply changes
        should_apply = args.apply

        if not should_apply:
            # Ask for confirmation only in interactive mode
            if sys.stdin.isatty():
                logger.info("\n" + "=" * 80)
                response = (
                    input("\nDo you want to apply these changes? (yes/no): ")
                    .strip()
                    .lower()
                )
                should_apply = response == "yes"
            else:
                logger.info("\nNon-interactive mode: Use --apply flag to apply changes")
                return 0

        if should_apply:
            logger.info("\n" + "=" * 80)
            logger.info("APPLYING CHANGES")
            logger.info("=" * 80 + "\n")
            migrate_evaluations(cursor, paper_dataset_mappings, dry_run=False)
            conn.commit()
            logger.info("\n✓ SUCCESS: Changes committed to database!")
        else:
            logger.info("\nMigration cancelled")
            conn.rollback()

        return 0

    except Exception as e:
        logger.error(f"Error during migration: {e}", exc_info=True)
        conn.rollback()
        return 1
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
