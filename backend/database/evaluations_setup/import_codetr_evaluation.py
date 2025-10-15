"""
Import CoDETR evaluation from legacy PapersWithCode evaluation-tables.json file.

This script imports CoDETR evaluations on COCO datasets to compare with DETR.
CoDETR paper arxiv_id: 2211.12860
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Parse a date string to a date object."""
    if not date_str:
        return None

    try:
        # Try parsing as YYYY-MM-DD
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Could not parse date: {date_str}")
        return None


def find_codetr_evaluations(evaluation_tables_file: Path) -> List[Dict]:
    """Find all CoDETR evaluations on COCO datasets from the evaluation tables."""
    logger.info(f"Loading evaluation tables from {evaluation_tables_file}")

    with open(evaluation_tables_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Find Object Detection task
    obj_det_task = None
    for item in data:
        if item.get("task") == "Object Detection":
            obj_det_task = item
            break

    if not obj_det_task:
        logger.error("Object Detection task not found in evaluation tables")
        return []

    logger.info("Found Object Detection task")

    # Search for CoDETR evaluations on COCO datasets
    codetr_evals = []
    for dataset in obj_det_task.get("datasets", []):
        dataset_name = dataset.get("dataset", "")

        # Only include COCO datasets (not LVIS or other datasets)
        if "coco" not in dataset_name.lower():
            continue

        logger.info(f"Checking dataset: {dataset_name}")

        # Search for CoDETR evaluation
        if "sota" in dataset and "rows" in dataset["sota"]:
            rows = dataset["sota"]["rows"]

            for row in rows:
                paper_url = row.get("paper_url", "")
                paper_title = row.get("paper_title", "")
                model_name = row.get("model_name", "")

                # Look for CoDETR (arxiv_id: 2211.12860)
                if "2211.12860" in paper_url:
                    logger.info(f"Found CoDETR evaluation on {dataset_name}:")
                    logger.info(f"  Paper: {paper_title}")
                    logger.info(f"  Model: {model_name}")
                    logger.info(f"  Metrics: {row.get('metrics', {})}")

                    codetr_evals.append(
                        {
                            "paper_url": paper_url,
                            "paper_title": paper_title,
                            "model_name": model_name,
                            "metrics": row.get("metrics", {}),
                            "uses_additional_data": row.get(
                                "uses_additional_data", False
                            ),
                            "paper_date": row.get("paper_date"),
                            "dataset_name": dataset_name,
                        }
                    )

    if not codetr_evals:
        logger.error("No CoDETR evaluations found on COCO datasets")

    return codetr_evals


def import_evaluation(db: Session, eval_data: Dict) -> Optional[DBEvaluation]:
    """Import an evaluation into the database."""

    # Extract arxiv_id from paper_url
    paper_url = eval_data.get("paper_url", "")
    arxiv_id = None
    if "arxiv.org/abs/" in paper_url:
        # Extract arxiv ID (e.g., "2211.12860" from "https://arxiv.org/abs/2211.12860v3")
        arxiv_id = paper_url.split("/")[-1].split("v")[0]

    if not arxiv_id:
        logger.error("Could not extract arxiv_id from paper URL")
        return None

    logger.info(f"Looking up paper with arxiv_id: {arxiv_id}")

    # Look up paper
    paper = (
        db.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version)
        .first()
    )

    if not paper:
        logger.error(f"Paper not found in database: {arxiv_id}")
        return None

    logger.info(f"Found paper: {paper.title} (ID: {paper.id})")

    # Look up task (Object Detection)
    task = db.query(DBTask).filter(DBTask.name == "Object Detection").first()

    if not task:
        logger.error("Object Detection task not found in database")
        return None

    logger.info(f"Found task: {task.name} (ID: {task.id})")

    # Look up dataset (COCO)
    # We use the existing COCO dataset which is named "COCO (Common Objects in Context)"
    dataset = db.query(DBDataset).filter(DBDataset.name.ilike("%COCO%")).first()

    if not dataset:
        logger.error("COCO dataset not found in database")
        return None

    logger.info(f"Found dataset: {dataset.name} (ID: {dataset.id})")

    # Check if evaluation already exists
    existing = (
        db.query(DBEvaluation)
        .filter(
            DBEvaluation.paper_id == paper.id,
            DBEvaluation.task_id == task.id,
            DBEvaluation.dataset_id == dataset.id,
            DBEvaluation.model_name == eval_data["model_name"],
        )
        .first()
    )

    if existing:
        logger.info(f"Evaluation already exists (ID: {existing.id})")
        return existing

    # Determine best metric (usually AP for object detection)
    metrics = eval_data.get("metrics", {})
    best_metric = "box AP" if "box AP" in metrics else "AP" if "AP" in metrics else None

    # Create the evaluation
    evaluation = DBEvaluation(
        paper_id=paper.id,
        task_id=task.id,
        dataset_id=dataset.id,
        model_name=eval_data.get("model_name"),
        methodology=None,  # Not provided in the data
        metrics=metrics,
        uses_additional_data=eval_data.get("uses_additional_data", False),
        best_rank=None,  # Not provided in the data
        best_metric=best_metric,
        evaluated_on=parse_date(eval_data.get("paper_date")),
        external_source_url=eval_data.get("paper_url"),
    )

    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    logger.info(f"Successfully imported evaluation (ID: {evaluation.id})")
    logger.info(f"  Paper: {paper.title}")
    logger.info(f"  Task: {task.name}")
    logger.info(f"  Dataset: {dataset.name}")
    logger.info(f"  Model: {evaluation.model_name}")
    logger.info(f"  Metrics: {evaluation.metrics}")

    return evaluation


def main():
    """Main function to import CoDETR evaluations."""
    # Path to the legacy PWC evaluation tables file
    eval_tables_file = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "legacy_pwc_data"
        / "evaluation-tables.json"
    )

    if not eval_tables_file.exists():
        logger.error(f"Evaluation tables file not found: {eval_tables_file}")
        return

    # Find all CoDETR evaluations on COCO
    codetr_eval_data = find_codetr_evaluations(eval_tables_file)
    if not codetr_eval_data:
        logger.error("Could not find CoDETR evaluations in the file")
        return

    logger.info(f"\nFound {len(codetr_eval_data)} CoDETR evaluations on COCO datasets")

    # Import to database
    session = db_manager.session_local()
    try:
        imported_evaluations = []
        for eval_data in codetr_eval_data:
            logger.info("\n" + "=" * 70)
            logger.info(
                f"Importing: {eval_data['model_name']} on {eval_data['dataset_name']}"
            )
            logger.info("=" * 70)

            evaluation = import_evaluation(session, eval_data)
            if evaluation:
                imported_evaluations.append(evaluation)

        # Print summary
        if imported_evaluations:
            logger.info("\n" + "=" * 70)
            logger.info("CoDETR Evaluations Import Summary")
            logger.info("=" * 70)
            logger.info(
                f"Successfully imported {len(imported_evaluations)} evaluations"
            )

            for evaluation in imported_evaluations:
                logger.info(f"\n  Evaluation ID: {evaluation.id}")
                logger.info(f"  Model Name: {evaluation.model_name}")
                logger.info(f"  Best Metric: {evaluation.best_metric}")
                logger.info(
                    f"  Uses Additional Data: {evaluation.uses_additional_data}"
                )
                logger.info(f"  Evaluated On: {evaluation.evaluated_on}")
                logger.info("  Metrics:")
                for metric_name, metric_value in evaluation.metrics.items():
                    logger.info(f"    {metric_name}: {metric_value}")

            logger.info("\n" + "=" * 70)
            logger.info("\n✓ SUCCESS: CoDETR evaluations imported successfully!")
            logger.info("\nYou can now query these evaluations via the API:")
            logger.info(
                f"  - GET /api/v1/evaluations/?paper_id={imported_evaluations[0].paper_id}"
            )
            logger.info(
                f"  - GET /api/v1/evaluations/?task_id={imported_evaluations[0].task_id}&dataset_id={imported_evaluations[0].dataset_id}"
            )
    except Exception as e:
        logger.error(f"Error importing evaluations: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
