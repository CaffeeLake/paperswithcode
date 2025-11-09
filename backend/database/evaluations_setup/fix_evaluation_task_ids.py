"""
Fix evaluation task_ids for paper 2509.17765.

The evaluations were incorrectly linked to task 12 (ASR) because step_4 created
datasets with the wrong task associations. This script updates evaluations to use
the correct task_ids based on each dataset's actual task associations.

Usage:
    uv run --env-file backend/keys.env python backend/database/evaluations_setup/fix_evaluation_task_ids.py
"""

import sys
import logging
from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Dataset as DBDataset,
    TaskDataset,
)
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fix_evaluation_task_ids(paper_id: int = 52888):
    """Fix task_ids for evaluations in paper 52888."""
    db = db_manager.session_local()
    try:
        # Get all evaluations for this paper
        evaluations = (
            db.query(DBEvaluation).filter(DBEvaluation.paper_id == paper_id).all()
        )

        logger.info(f"Found {len(evaluations)} evaluations for paper {paper_id}")

        service = EvaluationService(db)
        updates = []

        for eval in evaluations:
            if not eval.dataset_id:
                logger.warning(f"Evaluation {eval.id} has no dataset_id, skipping")
                continue

            # Get tasks associated with this dataset
            task_ids = (
                db.query(TaskDataset.task_id)
                .filter(TaskDataset.dataset_id == eval.dataset_id)
                .all()
            )
            dataset_task_ids = [tid[0] for tid in task_ids]

            if not dataset_task_ids:
                logger.warning(
                    f"Dataset {eval.dataset_id} has no task associations, skipping evaluation {eval.id}"
                )
                continue

            # Use the first task (or check if current task_id is correct)
            correct_task_id = dataset_task_ids[0]

            if eval.task_id != correct_task_id:
                dataset = (
                    db.query(DBDataset).filter(DBDataset.id == eval.dataset_id).first()
                )
                dataset_name = dataset.name if dataset else f"ID {eval.dataset_id}"

                # Check if we need to normalize metrics
                # Some tasks require "Accuracy" but evaluations might have "score"
                metrics_to_update = None
                best_metric_to_update = None

                # Normalize "score" to "Accuracy" for tasks that require it
                if eval.best_metric and eval.best_metric.lower() == "score":
                    # Check if the target task requires Accuracy
                    from backend.services.leaderboard_metric_service import (
                        LeaderboardMetricService,
                    )

                    metric_service = LeaderboardMetricService(db)
                    is_valid, error_message = (
                        metric_service.validate_metrics_for_leaderboard(
                            correct_task_id,
                            eval.dataset_id,
                            ["Accuracy"],
                            "Accuracy",
                        )
                    )
                    if is_valid:
                        # Normalize score to Accuracy
                        metrics_dict = dict(eval.metrics) if eval.metrics else {}
                        if "score" in metrics_dict or "Score" in metrics_dict:
                            score_value = metrics_dict.get("score") or metrics_dict.get(
                                "Score"
                            )
                            metrics_dict = {"Accuracy": score_value}
                            metrics_to_update = metrics_dict
                            best_metric_to_update = "Accuracy"
                            logger.info(
                                f"  Will normalize 'score' → 'Accuracy' for task {correct_task_id}"
                            )

                logger.info(
                    f"Evaluation {eval.id} ({dataset_name}): "
                    f"task_id {eval.task_id} → {correct_task_id}"
                )
                updates.append(
                    (
                        eval.id,
                        correct_task_id,
                        dataset_name,
                        metrics_to_update,
                        best_metric_to_update,
                    )
                )

        # Apply updates
        for (
            eval_id,
            new_task_id,
            dataset_name,
            metrics_to_update,
            best_metric_to_update,
        ) in updates:
            try:
                update_kwargs = {"task_id": new_task_id}
                if metrics_to_update:
                    update_kwargs["metrics"] = metrics_to_update
                if best_metric_to_update:
                    update_kwargs["best_metric"] = best_metric_to_update

                service.update_evaluation(evaluation_id=eval_id, **update_kwargs)
                logger.info(
                    f"✓ Updated evaluation {eval_id} ({dataset_name}) to task {new_task_id}"
                )
            except Exception as e:
                logger.error(f"✗ Failed to update evaluation {eval_id}: {e}")

        db.commit()
        logger.info(f"\n✓ Successfully updated {len(updates)} evaluations")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error during update: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    success = fix_evaluation_task_ids()
    sys.exit(0 if success else 1)
