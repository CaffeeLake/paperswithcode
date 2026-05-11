#!/usr/bin/env python3
"""
Import Gemini 2.5 evaluation results.

This script adds evaluation results for Gemini 2.5 Pro and Gemini 2.5 Flash
from the paper "Gemini 2.5: Pushing the Frontier with Advanced Reasoning,
Multimodality, Long Context, and Next Generation Agentic Capabilities"
(arXiv:2507.06261).

Evaluations are added for benchmarks that exist in the database.
"""

import sys

from sqlalchemy.orm import Session
from database.connection import db_manager
from services.evaluation_service import EvaluationService
from models.database import Paper as DBPaper
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Gemini 2.5 paper details
GEMINI_PAPER_ARXIV_ID = "2507.06261"
EXTERNAL_SOURCE_URL = "https://arxiv.org/abs/2507.06261"

# Evaluation data: (dataset_id, task_id, dataset_name, flash_score, pro_score, notes)
EVALUATIONS = [
    # Code benchmarks
    (95, 15, "LiveCodeBench", 59.3, 74.2, ""),
    (22, 15, "SWE-Bench Verified (single attempt)", 48.9, 59.6, "single_attempt"),
    (22, 15, "SWE-Bench Verified (multiple attempts)", 60.3, 67.2, "multiple_attempts"),
    # Language modeling / reasoning
    (38, 5, "GPQA Diamond", 82.8, 86.4, ""),
    (43, 5, "SimpleQA", 26.9, 54.0, ""),
    (83, 5, "FACTS Grounding", 85.3, 87.8, ""),
    (17, 5, "AIME 2025", 72.0, 88.0, ""),
    # General
    (82, 256, "Humanity's Last Exam", 11.0, 21.6, ""),
    # Image understanding
    (31, 8, "MMMU", 79.7, 82.0, ""),
    (64, 8, "ZeroBench", 2.0, 4.5, ""),
]


def get_gemini_paper_id(db: Session) -> int:
    """Get the database ID for the Gemini 2.5 paper."""
    paper = (
        db.query(DBPaper)
        .filter(DBPaper.arxiv_id == GEMINI_PAPER_ARXIV_ID, DBPaper.is_latest_version)
        .first()
    )

    if not paper:
        raise ValueError(
            f"Gemini 2.5 paper not found (ArXiv ID: {GEMINI_PAPER_ARXIV_ID})"
        )

    logger.info(f"Found Gemini 2.5 paper: ID={paper.id}, Title='{paper.title}'")
    return paper.id


def import_evaluations(db: Session):
    """Import all Gemini 2.5 evaluation results."""

    try:
        # Get paper ID
        paper_id = get_gemini_paper_id(db)

        # Initialize evaluation service
        service = EvaluationService(db)

        # Track statistics
        flash_added = 0
        pro_added = 0
        flash_errors = 0
        pro_errors = 0

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Starting import of {len(EVALUATIONS)} benchmarks for both models")
        logger.info(f"{'=' * 80}\n")

        for (
            dataset_id,
            task_id,
            dataset_name,
            flash_score,
            pro_score,
            notes,
        ) in EVALUATIONS:
            # Determine methodology based on notes
            methodology = None
            model_suffix = ""

            if notes == "single_attempt":
                methodology = "Single attempt"
                model_suffix = " (single attempt)"
            elif notes == "multiple_attempts":
                methodology = "Multiple attempts"
                model_suffix = " (multiple attempts)"

            logger.info(f"Processing: {dataset_name}")
            logger.info(f"  Dataset ID: {dataset_id}, Task ID: {task_id}")

            # Add Gemini 2.5 Flash evaluation
            try:
                flash_model_name = f"Gemini 2.5 Flash{model_suffix}"
                logger.info(f"  Adding {flash_model_name}: {flash_score}%")

                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=task_id,
                    dataset_id=dataset_id,
                    model_name=flash_model_name,
                    methodology=methodology,
                    metrics={"Accuracy": str(flash_score)},
                    uses_additional_data=False,
                    best_metric="Accuracy",
                    external_source_url=EXTERNAL_SOURCE_URL,
                )

                flash_added += 1
                logger.info("  ✓ Added Gemini 2.5 Flash")

            except Exception as e:
                flash_errors += 1
                logger.error(f"  ✗ Failed to add Gemini 2.5 Flash: {e}")

            # Add Gemini 2.5 Pro evaluation
            try:
                pro_model_name = f"Gemini 2.5 Pro{model_suffix}"
                logger.info(f"  Adding {pro_model_name}: {pro_score}%")

                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=task_id,
                    dataset_id=dataset_id,
                    model_name=pro_model_name,
                    methodology=methodology,
                    metrics={"Accuracy": str(pro_score)},
                    uses_additional_data=False,
                    best_metric="Accuracy",
                    external_source_url=EXTERNAL_SOURCE_URL,
                )

                pro_added += 1
                logger.info("  ✓ Added Gemini 2.5 Pro")

            except Exception as e:
                pro_errors += 1
                logger.error(f"  ✗ Failed to add Gemini 2.5 Pro: {e}")

            logger.info("")  # Blank line between datasets

        # Print summary
        logger.info(f"\n{'=' * 80}")
        logger.info("Import Summary")
        logger.info(f"{'=' * 80}")
        logger.info(f"Gemini 2.5 Flash: {flash_added} added, {flash_errors} errors")
        logger.info(f"Gemini 2.5 Pro:   {pro_added} added, {pro_errors} errors")
        logger.info(f"Total:            {flash_added + pro_added} evaluations added")
        logger.info(f"{'=' * 80}\n")

        return flash_added + pro_added > 0

    except Exception as e:
        logger.error(f"Fatal error during import: {e}")
        raise


def main():
    """Main entry point."""
    logger.info("Gemini 2.5 Evaluation Import Script")
    logger.info("=" * 80)

    db = db_manager.session_local()

    try:
        success = import_evaluations(db)

        if success:
            logger.info("✓ Import completed successfully!")
            return 0
        else:
            logger.error("✗ Import failed - no evaluations were added")
            return 1

    except Exception as e:
        logger.error(f"✗ Import failed with error: {e}")
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
