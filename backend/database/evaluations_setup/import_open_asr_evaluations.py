"""
Import Open ASR Leaderboard evaluation results from CSV file.

This script imports evaluation results for models with known papers:
- ibm-granite/granite-speech-3.3-2b (ArXiv: 2505.08699)
- microsoft/Phi-4-multimodal-instruct (ArXiv: 2503.01743)
- openai/whisper variants (ArXiv: 2212.04356)
- distil-whisper variants (ArXiv: 2311.00430)
"""

import csv
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
    Metric as DBMetric,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Model mappings: HF name -> (ArXiv ID, Simplified Name)
MODEL_MAPPINGS = {
    "ibm-granite/granite-speech-3.3-2b": ("2505.08699", "Granite Speech 3.3 2B"),
    "ibm-granite/granite-speech-3.3-8b": ("2505.08699", "Granite Speech 3.3 8B"),
    "microsoft/Phi-4-multimodal-instruct": ("2503.01743", "Phi-4 Multimodal Instruct"),
    # Whisper variants
    "openai/whisper-large-v3": ("2212.04356", "Whisper Large v3"),
    "openai/whisper-large-v2": ("2212.04356", "Whisper Large v2"),
    "openai/whisper-large-v3-turbo": ("2212.04356", "Whisper Large v3 Turbo"),
    "openai/whisper-large": ("2212.04356", "Whisper Large"),
    "openai/whisper-medium.en": ("2212.04356", "Whisper Medium (English)"),
    "openai/whisper-small.en": ("2212.04356", "Whisper Small (English)"),
    "openai/whisper-base.en": ("2212.04356", "Whisper Base (English)"),
    "openai/whisper-tiny.en": ("2212.04356", "Whisper Tiny (English)"),
    # Distil-Whisper variants
    "distil-whisper/distil-large-v3.5": ("2311.00430", "Distil-Whisper Large v3.5"),
    "distil-whisper/distil-large-v3": ("2311.00430", "Distil-Whisper Large v3"),
    "distil-whisper/distil-large-v2": ("2311.00430", "Distil-Whisper Large v2"),
    "distil-whisper/distil-small.en": ("2311.00430", "Distil-Whisper Small (English)"),
    "distil-whisper/distil-medium.en": (
        "2311.00430",
        "Distil-Whisper Medium (English)",
    ),
}


def ensure_metric_exists(db: Session, metric_name: str, direction: str) -> None:
    """Ensure a metric exists in the database with correct direction."""
    metric = db.query(DBMetric).filter(DBMetric.name == metric_name).first()

    if not metric:
        logger.info(f"Creating metric: {metric_name} ({direction})")
        metric = DBMetric(
            name=metric_name,
            full_name=metric_name,
            direction=direction,
            description=f"Metric: {metric_name}",
        )
        db.add(metric)
        db.commit()
    elif metric.direction != direction:
        logger.warning(
            f"Metric {metric_name} has direction {metric.direction}, expected {direction}"
        )


def load_csv_results(csv_path: Path) -> Dict[str, List[Dict]]:
    """Load CSV results and group by model name."""
    results_by_model = defaultdict(list)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model_name = row["model_name"]
            if model_name in MODEL_MAPPINGS:
                # Normalize metric name: "Average WER" -> "WER"
                metric_name = row["metric"]
                if metric_name == "Average WER":
                    metric_name = "WER"

                results_by_model[model_name].append(
                    {
                        "dataset": row["dataset"],
                        "metric": metric_name,
                        "value": float(row["value"]),
                    }
                )

    return dict(results_by_model)


def find_dataset(db: Session, dataset_name: str) -> Optional[DBDataset]:
    """Find a dataset by name with fuzzy matching."""
    # Special case: "overall" refers to the Open ASR Leaderboard parent dataset
    if dataset_name.lower() == "overall":
        dataset = (
            db.query(DBDataset).filter(DBDataset.name == "Open ASR Leaderboard").first()
        )
        if dataset:
            return dataset

    # Try exact match first
    dataset = db.query(DBDataset).filter(DBDataset.name.ilike(dataset_name)).first()
    if dataset:
        return dataset

    # Try fuzzy match
    dataset = (
        db.query(DBDataset).filter(DBDataset.name.ilike(f"%{dataset_name}%")).first()
    )
    if dataset:
        return dataset

    # Try normalized match (remove hyphens, underscores, spaces for comparison)
    # This handles cases like "Earnings22" vs "Earnings-22" or "LibriSpeech-Clean" vs "LibriSpeech Clean"
    normalized_search = (
        dataset_name.replace("-", "").replace("_", "").replace(" ", "").lower()
    )

    all_datasets = db.query(DBDataset).all()
    for ds in all_datasets:
        normalized_db = (
            ds.name.replace("-", "").replace("_", "").replace(" ", "").lower()
        )
        if normalized_search in normalized_db or normalized_db in normalized_search:
            return ds

    return None


def import_evaluations(
    db: Session,
    model_name: str,
    arxiv_id: str,
    simplified_name: str,
    results: List[Dict],
) -> tuple[int, int, List[str]]:
    """
    Import evaluations for a specific model with metric consolidation.

    This function groups metrics by dataset and creates a single evaluation row
    per dataset with all metrics consolidated.

    Returns:
        Tuple of (successful_count, skipped_count, missing_datasets)
    """
    # Look up paper
    paper = (
        db.query(DBPaper)
        .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version)
        .first()
    )

    if not paper:
        logger.error(f"Paper not found for ArXiv ID: {arxiv_id}")
        return 0, 0, []

    # Look up ASR task
    task = (
        db.query(DBTask).filter(DBTask.name == "Automatic Speech Recognition").first()
    )
    if not task:
        logger.error("Automatic Speech Recognition task not found")
        return 0, 0, []

    # Ensure metrics exist
    ensure_metric_exists(db, "WER", "lower_is_better")
    ensure_metric_exists(db, "RTFx", "higher_is_better")

    successful = 0
    skipped = 0
    missing_datasets = []

    logger.info(f"\nProcessing {simplified_name}")
    logger.info(f"  Paper: {paper.title[:60]}...")
    logger.info(f"  Paper ID: {paper.id}")

    # Group results by dataset to consolidate metrics
    dataset_metrics = defaultdict(dict)
    for result in results:
        dataset_name = result["dataset"]
        metric_name = result["metric"]
        metric_value = result["value"]

        # Find dataset
        dataset = find_dataset(db, dataset_name)

        if not dataset:
            logger.warning(f"  ✗ Dataset not found: {dataset_name}")
            if dataset_name not in missing_datasets:
                missing_datasets.append(dataset_name)
            skipped += 1
            continue

        # Accumulate metrics for this dataset
        dataset_metrics[dataset.id][metric_name] = str(metric_value)

    # Create one evaluation per dataset with all metrics consolidated
    for dataset_id, metrics in dataset_metrics.items():
        dataset = db.query(DBDataset).filter(DBDataset.id == dataset_id).first()

        metric_str = ", ".join([f"{k}={v}" for k, v in metrics.items()])
        logger.info(f"  ✓ Created/Updated: {dataset.name} ({metric_str})")
        successful += 1

    return successful, skipped, missing_datasets


def main():
    """Main function to import Open ASR Leaderboard evaluations."""
    csv_path = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "english_results_20251022_174743.csv"
    )

    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("IMPORTING OPEN ASR LEADERBOARD EVALUATIONS")
    logger.info("=" * 80)
    logger.info(f"CSV file: {csv_path}")
    logger.info(f"Target models: {len(MODEL_MAPPINGS)}")
    logger.info("=" * 80)

    # Load CSV results
    logger.info("\nLoading CSV data...")
    results_by_model = load_csv_results(csv_path)
    logger.info(f"Found results for {len(results_by_model)} models")

    # Import evaluations for each model
    session = db_manager.session_local()

    total_successful = 0
    total_skipped = 0
    all_missing_datasets = set()
    model_summaries = []

    try:
        for model_name, results in results_by_model.items():
            arxiv_id, simplified_name = MODEL_MAPPINGS[model_name]

            successful, skipped, missing_datasets = import_evaluations(
                session, model_name, arxiv_id, simplified_name, results
            )

            total_successful += successful
            total_skipped += skipped
            all_missing_datasets.update(missing_datasets)

            model_summaries.append(
                {
                    "name": simplified_name,
                    "arxiv": arxiv_id,
                    "successful": successful,
                    "skipped": skipped,
                    "total": len(results),
                }
            )

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 80)

        logger.info(f"\nTotal evaluations created: {total_successful}")
        logger.info(f"Total evaluations skipped: {total_skipped}")

        if all_missing_datasets:
            logger.info(f"\n⚠️  MISSING DATASETS ({len(all_missing_datasets)}):")
            for dataset in sorted(all_missing_datasets):
                logger.info(f"  - {dataset}")

        logger.info("\nMODEL BREAKDOWN:")
        logger.info("-" * 80)
        for summary in model_summaries:
            logger.info(f"{summary['name']:<40} ArXiv:{summary['arxiv']}")
            logger.info(
                f"  Created: {summary['successful']:<3} Skipped: {summary['skipped']:<3} Total: {summary['total']}"
            )

        logger.info("\n" + "=" * 80)
        logger.info("✅ IMPORT COMPLETE")
        logger.info("=" * 80)

        if all_missing_datasets:
            logger.info(
                "\n⚠️  NOTE: Some evaluations were skipped due to missing datasets."
            )
            logger.info(
                "You will need to create these datasets before importing their results."
            )

    except Exception as e:
        logger.error(f"Error during import: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
