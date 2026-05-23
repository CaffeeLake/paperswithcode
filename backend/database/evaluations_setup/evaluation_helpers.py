"""
Helper functions for evaluation data import and consolidation.

This module provides utilities to ensure evaluation data is properly consolidated,
with all metrics for a model stored in a single row rather than split across
multiple rows.
"""

import logging
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from backend.models.database import Evaluation as DBEvaluation

logger = logging.getLogger(__name__)


def consolidate_metrics_for_model(metric_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Consolidate multiple metric dictionaries into a single dictionary.

    Args:
        metric_list: List of metric dictionaries, e.g. [{"WER": "5.2"}, {"RTFx": "0.8"}]

    Returns:
        Single consolidated dictionary, e.g. {"WER": "5.2", "RTFx": "0.8"}

    Example:
        >>> consolidate_metrics_for_model([{"WER": "5.2"}, {"RTFx": "0.8"}])
        {"WER": "5.2", "RTFx": "0.8"}
    """
    consolidated = {}
    for metrics in metric_list:
        if metrics:
            consolidated.update(metrics)
    return consolidated


def get_or_create_evaluation(
    db: Session,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_name: str,
    metrics: Dict[str, Any],
    methodology: Optional[str] = None,
    uses_additional_data: bool = False,
    best_rank: Optional[int] = None,
    best_metric: Optional[str] = None,
    evaluated_on: Optional[Any] = None,
    external_source_url: Optional[str] = None,
    num_parameters: Optional[int] = None,
    merge_metrics: bool = True,
) -> DBEvaluation:
    """
    Get or create an evaluation, merging metrics if it already exists.

    This function ensures that evaluations are properly consolidated. If an evaluation
    already exists for the given (paper_id, task_id, dataset_id, model_name) combination,
    it will merge the new metrics with existing ones rather than creating a duplicate row.

    Args:
        db: Database session
        paper_id: Paper ID
        task_id: Task ID
        dataset_id: Dataset ID
        model_name: Model name (used as unique identifier)
        metrics: Dictionary of metrics to add/merge
        methodology: Optional methodology description
        uses_additional_data: Whether additional training data was used
        best_rank: Best rank achieved on this dataset
        best_metric: Primary metric for ranking
        evaluated_on: Evaluation date
        external_source_url: Source URL for results
        merge_metrics: If True, merge new metrics with existing ones. If False, replace.

    Returns:
        The evaluation object (either existing or newly created)

    Example:
        >>> # First call creates new evaluation
        >>> eval1 = get_or_create_evaluation(
        ...     db, paper_id=1, task_id=2, dataset_id=3, model_name="Whisper v2",
        ...     metrics={"WER": "5.2"}
        ... )
        >>>
        >>> # Second call merges metrics into existing evaluation
        >>> eval2 = get_or_create_evaluation(
        ...     db, paper_id=1, task_id=2, dataset_id=3, model_name="Whisper v2",
        ...     metrics={"RTFx": "0.8"}
        ... )
        >>> # eval2.metrics now contains: {"WER": "5.2", "RTFx": "0.8"}
    """
    # Check if evaluation already exists
    existing = (
        db.query(DBEvaluation)
        .filter(
            DBEvaluation.paper_id == paper_id,
            DBEvaluation.task_id == task_id,
            DBEvaluation.dataset_id == dataset_id,
            DBEvaluation.model_name == model_name,
        )
        .first()
    )

    if existing:
        logger.debug(
            f"Found existing evaluation for {model_name} on dataset {dataset_id}"
        )

        # Merge metrics
        if merge_metrics:
            existing_metrics = existing.metrics or {}
            merged_metrics = {**existing_metrics, **metrics}
            existing.metrics = merged_metrics
            logger.debug(
                f"Merged metrics: {existing_metrics} + {metrics} = {merged_metrics}"
            )
        else:
            existing.metrics = metrics

        # Update other fields if they are provided and existing values are None
        if methodology and not existing.methodology:
            existing.methodology = methodology
        if best_rank is not None and existing.best_rank is None:
            existing.best_rank = best_rank
        if best_metric and not existing.best_metric:
            existing.best_metric = best_metric
        if evaluated_on and not existing.evaluated_on:
            existing.evaluated_on = evaluated_on
        if external_source_url and not existing.external_source_url:
            existing.external_source_url = external_source_url
        if num_parameters is not None and existing.num_parameters is None:
            existing.num_parameters = num_parameters

        db.add(existing)
        db.commit()
        db.refresh(existing)

        # Recalculate ranks for this leaderboard after update
        from backend.services.evaluation_service import EvaluationService

        service = EvaluationService(db)
        service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            metric_name=best_metric or existing.best_metric,
        )

        # Refresh to get updated rank
        db.refresh(existing)

        return existing

    else:
        logger.debug(
            f"Creating new evaluation for {model_name} on dataset {dataset_id}"
        )

        # Create new evaluation
        evaluation = DBEvaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=model_name,
            methodology=methodology,
            metrics=metrics,
            uses_additional_data=uses_additional_data,
            best_rank=best_rank,
            best_metric=best_metric,
            evaluated_on=evaluated_on,
            external_source_url=external_source_url,
            num_parameters=num_parameters,
        )

        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)

        # Recalculate ranks for this leaderboard after creation
        from backend.services.evaluation_service import EvaluationService

        service = EvaluationService(db)
        service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            metric_name=best_metric,
        )

        # Refresh to get updated rank
        db.refresh(evaluation)

        return evaluation


def bulk_create_evaluations_with_consolidation(
    db: Session, evaluations_data: List[Dict[str, Any]], commit_batch_size: int = 50
) -> tuple[int, int]:
    """
    Bulk create evaluations with automatic metric consolidation.

    This function groups evaluation data by (paper_id, task_id, dataset_id, model_name)
    and consolidates metrics before creating database entries.

    Args:
        db: Database session
        evaluations_data: List of evaluation data dictionaries
        commit_batch_size: Number of evaluations to commit at once

    Returns:
        Tuple of (created_count, merged_count)

    Example:
        >>> data = [
        ...     {"paper_id": 1, "task_id": 2, "dataset_id": 3, "model_name": "Model A", "metrics": {"WER": "5.2"}},
        ...     {"paper_id": 1, "task_id": 2, "dataset_id": 3, "model_name": "Model A", "metrics": {"RTFx": "0.8"}},
        ...     {"paper_id": 1, "task_id": 2, "dataset_id": 4, "model_name": "Model B", "metrics": {"AP": "45.2"}},
        ... ]
        >>> created, merged = bulk_create_evaluations_with_consolidation(db, data)
        >>> # Result: 2 evaluations created (Model A with merged metrics, Model B)
    """
    # Group evaluations by unique key
    grouped = {}
    for eval_data in evaluations_data:
        key = (
            eval_data["paper_id"],
            eval_data["task_id"],
            eval_data["dataset_id"],
            eval_data["model_name"],
        )

        if key not in grouped:
            grouped[key] = {
                "paper_id": eval_data["paper_id"],
                "task_id": eval_data["task_id"],
                "dataset_id": eval_data["dataset_id"],
                "model_name": eval_data["model_name"],
                "metrics": {},
                "methodology": eval_data.get("methodology"),
                "uses_additional_data": eval_data.get("uses_additional_data", False),
                "best_rank": eval_data.get("best_rank"),
                "best_metric": eval_data.get("best_metric"),
                "evaluated_on": eval_data.get("evaluated_on"),
                "external_source_url": eval_data.get("external_source_url"),
                "num_parameters": eval_data.get("num_parameters"),
            }

        # Merge metrics
        if "metrics" in eval_data:
            grouped[key]["metrics"].update(eval_data["metrics"])

    created_count = 0
    merged_count = len(evaluations_data) - len(grouped)

    # Track leaderboards that need rank recalculation
    affected_leaderboards = set()

    # Create evaluations
    batch = []
    for eval_data in grouped.values():
        eval = get_or_create_evaluation(db, **eval_data)
        batch.append(eval)
        created_count += 1

        # Track this leaderboard for rank recalculation
        affected_leaderboards.add((eval.task_id, eval.dataset_id, eval.best_metric))

        if len(batch) >= commit_batch_size:
            batch = []

    # Recalculate ranks for all affected leaderboards
    from backend.services.evaluation_service import EvaluationService

    service = EvaluationService(db)

    logger.info(f"Recalculating ranks for {len(affected_leaderboards)} leaderboards...")
    for task_id, dataset_id, best_metric in affected_leaderboards:
        try:
            service.recalculate_ranks(
                task_id=task_id,
                dataset_id=dataset_id,
                metric_name=best_metric,
            )
        except Exception as e:
            logger.error(
                f"Failed to recalculate ranks for task={task_id}, dataset={dataset_id}, metric={best_metric}: {e}"
            )

    return created_count, merged_count
