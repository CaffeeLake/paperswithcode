#!/usr/bin/env python3
"""
Migrate TauBench evaluations to TauBench (retail) and TauBench (airline) datasets.

This script:
1. Finds existing TauBench dataset and evaluations
2. Checks if TauBench (retail) and TauBench (airline) datasets exist, creates them if not
3. Migrates evaluations based on metrics (retail vs airline)
4. For paper 2508.06471: 79.7 -> TauBench (retail), 60.4 -> TauBench (airline)
"""

import sys
import logging
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.database.connection import db_manager
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    TaskDataset,
)
from backend.models.api import DatasetCreateRequest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def find_taubench_dataset(db: Session) -> Optional[DBDataset]:
    """Find the existing TauBench dataset."""
    # Find all TauBench datasets
    all_datasets = (
        db.query(DBDataset)
        .filter(
            or_(
                DBDataset.name.ilike("%TauBench%"),
                DBDataset.full_name.ilike("%TauBench%"),
            )
        )
        .all()
    )

    # Return the one that's NOT a variant (doesn't contain retail or airline)
    for dataset in all_datasets:
        name_lower = (dataset.name or "").lower()
        if "retail" not in name_lower and "airline" not in name_lower:
            return dataset

    # If all are variants, return None
    return None


def find_or_create_taubench_variant(
    db: Session, variant_name: str, variant_type: str, task_ids: List[int]
) -> DBDataset:
    """Find or create a TauBench variant dataset."""
    # Check if it already exists - look for datasets with TauBench and the variant type
    all_datasets = (
        db.query(DBDataset)
        .filter(
            or_(
                DBDataset.name.ilike("%TauBench%"),
                DBDataset.full_name.ilike("%TauBench%"),
            )
        )
        .all()
    )

    # Find the variant
    for dataset in all_datasets:
        name_lower = (dataset.name or "").lower()
        if variant_type.lower() in name_lower:
            logger.info(f"Found existing dataset: {dataset.name} (ID: {dataset.id})")
            return dataset

    # Create new dataset
    logger.info(f"Creating new dataset: {variant_name}")
    service = DatasetService(db)
    request = DatasetCreateRequest(
        name=variant_name,
        full_name=variant_name,
        description=f"TauBench {variant_type} variant benchmark dataset",
        url=None,
        hf_url=None,
        paper_url=None,
        task_ids=task_ids,
    )

    created_dataset = service.create_dataset(request)
    logger.info(f"Created dataset: {created_dataset.name} (ID: {created_dataset.id})")

    # Return the database object
    return db.query(DBDataset).filter(DBDataset.id == int(created_dataset.id)).first()


def get_taubench_evaluations(db: Session, dataset_id: int) -> List[DBEvaluation]:
    """Get all evaluations for TauBench dataset."""
    evaluations = (
        db.query(DBEvaluation).filter(DBEvaluation.dataset_id == dataset_id).all()
    )
    return evaluations


def migrate_evaluation(
    db: Session,
    evaluation: DBEvaluation,
    target_dataset_id: int,
    evaluation_service: EvaluationService,
) -> bool:
    """Migrate an evaluation to a new dataset."""
    try:
        # Update the evaluation's dataset_id
        evaluation_service.update_evaluation(
            evaluation_id=evaluation.id,
            dataset_id=target_dataset_id,
        )
        logger.info(
            f"Migrated evaluation {evaluation.id} to dataset {target_dataset_id}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to migrate evaluation {evaluation.id}: {e}")
        return False


def get_paper_evaluations_mapping() -> Dict[str, Dict[str, str]]:
    """
    Return paper-specific mappings of metric values to variants.

    Format: {arxiv_id: {metric_value: variant}}
    """
    return {
        "2508.06471": {
            "79.7": "retail",
            "60.4": "airline",
        }
    }


def main():
    """Main migration function."""
    logger.info("Starting TauBench evaluation migration...")

    with db_manager.session_local() as db:
        # Step 1: Find existing TauBench dataset
        taubench_dataset = find_taubench_dataset(db)
        if not taubench_dataset:
            logger.error("TauBench dataset not found!")
            return 1

        logger.info(
            f"Found TauBench dataset: {taubench_dataset.name} (ID: {taubench_dataset.id})"
        )

        # Step 2: Get task IDs from existing dataset
        task_ids = (
            db.query(TaskDataset.task_id)
            .filter(TaskDataset.dataset_id == taubench_dataset.id)
            .all()
        )
        task_ids = [tid[0] for tid in task_ids]

        if not task_ids:
            logger.warning(
                "No tasks found for TauBench dataset. Using default task ID 5 (General Language Understanding)"
            )
            task_ids = [5]  # Default to General Language Understanding

        logger.info(f"Found task IDs: {task_ids}")

        # Step 3: Find or create variant datasets
        retail_dataset = find_or_create_taubench_variant(
            db, "TauBench (retail)", "retail", task_ids
        )
        airline_dataset = find_or_create_taubench_variant(
            db, "TauBench (airline)", "airline", task_ids
        )

        # Step 4: Get all evaluations for TauBench
        evaluations = get_taubench_evaluations(db, taubench_dataset.id)
        logger.info(f"Found {len(evaluations)} evaluations to migrate")

        if not evaluations:
            logger.info("No evaluations found to migrate")
            return 0

        # Step 5: Get paper-specific mappings
        paper_mappings = get_paper_evaluations_mapping()

        # Step 6: Migrate evaluations
        evaluation_service = EvaluationService(db)
        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for eval_obj in evaluations:
            # Get paper ArXiv ID
            paper = db.query(DBPaper).filter(DBPaper.id == eval_obj.paper_id).first()
            arxiv_id = paper.arxiv_id if paper else None

            # Determine target dataset
            target_dataset_id = None

            # Check if we have paper-specific mapping
            if arxiv_id and arxiv_id in paper_mappings:
                mapping = paper_mappings[arxiv_id]
                metrics = eval_obj.metrics or {}

                # Find matching metric value
                for metric_name, value in metrics.items():
                    try:
                        # Clean the value (handle strings like "79.7" or "79.7 ± 0.1")
                        if isinstance(value, str):
                            clean_val = value.split("±")[0].strip()
                            float_val = float(clean_val)
                        else:
                            float_val = float(value)

                        # Check against mapping values
                        for mapped_value_str, variant in mapping.items():
                            mapped_value = float(mapped_value_str)
                            if abs(float_val - mapped_value) < 0.1:
                                target_dataset_id = (
                                    retail_dataset.id
                                    if variant == "retail"
                                    else airline_dataset.id
                                )
                                logger.info(
                                    f"Matched value {value} to {variant} variant "
                                    f"(mapped value: {mapped_value_str})"
                                )
                                break

                        if target_dataset_id:
                            break
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Could not parse metric value {value}: {e}")
                        continue

            # If no specific mapping found, use heuristic (higher score = retail)
            if not target_dataset_id:
                metrics = eval_obj.metrics or {}
                metric_values = []
                for v in metrics.values():
                    try:
                        if isinstance(v, str):
                            clean_val = v.split("±")[0].strip()
                            metric_values.append(float(clean_val))
                        else:
                            metric_values.append(float(v))
                    except (ValueError, TypeError):
                        pass

                if metric_values:
                    max_value = max(metric_values)
                    # Heuristic: higher scores tend to be retail
                    # But this is imperfect - we'll log for manual review
                    logger.warning(
                        f"Evaluation {eval_obj.id} (paper {arxiv_id}) has no specific mapping. "
                        f"Max metric value: {max_value}. Skipping for manual review."
                    )
                    skipped_count += 1
                    continue

            if target_dataset_id:
                success = migrate_evaluation(
                    db, eval_obj, target_dataset_id, evaluation_service
                )
                if success:
                    migrated_count += 1
                else:
                    error_count += 1
            else:
                logger.warning(
                    f"Could not determine target dataset for evaluation {eval_obj.id}"
                )
                skipped_count += 1

        logger.info(
            f"\nMigration complete:\n"
            f"  - Migrated: {migrated_count}\n"
            f"  - Skipped: {skipped_count}\n"
            f"  - Errors: {error_count}"
        )

        if skipped_count > 0:
            logger.warning(
                f"\n{skipped_count} evaluations were skipped and need manual review."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
