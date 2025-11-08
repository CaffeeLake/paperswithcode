"""
Agent tools for the evaluation extraction pipeline.

This module consolidates all @function_tool definitions used across different steps.
Tools are organized by category:
- Task and dataset lookup tools
- Dataset search and management tools
- Evaluation management tools
"""

import json
import logging
from typing import List, Optional, Tuple

from agents import function_tool
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.api import DatasetCreateRequest
from backend.models.database import (
    Area as DBArea,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    Paper as DBPaper,
    Task as DBTask,
    TaskDatasetMetric as DBTaskDatasetMetric,
)
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_metric_service import LeaderboardMetricService

logger = logging.getLogger(__name__)


# ============================================================================
# Task and Dataset Lookup Tools
# ============================================================================


def get_datasets_for_task(task_id: int) -> str:
    """Get all datasets associated with a specific task.

    This function queries the database to find all datasets that are linked to
    a given task. This is useful for understanding which datasets are commonly
    used for a particular task when extracting evaluation results.

    Args:
        task_id: The ID of the task to get datasets for

    Returns:
        Formatted string with dataset information, or error message if task not found
    """
    session: Session = db_manager.session_local()

    try:
        # Check if task exists and load datasets relationship
        from sqlalchemy.orm import joinedload

        task = (
            session.query(DBTask)
            .options(joinedload(DBTask.datasets))
            .filter(DBTask.id == task_id)
            .first()
        )
        if not task:
            session.close()
            return f"Task with ID {task_id} not found"

        # Get datasets from the relationship and sort by name
        datasets = sorted(task.datasets, key=lambda d: d.name) if task.datasets else []

        if not datasets:
            session.close()
            return f"Task '{task.name}' (ID: {task_id}) has no associated datasets"

        # Format response
        response = f"Datasets for Task '{task.name}' (ID: {task_id}):\n"
        response += "=" * 60 + "\n\n"

        for dataset in datasets:
            response += f"- ID: {dataset.id:<4} - {dataset.name}"
            if dataset.full_name:
                response += f" ({dataset.full_name})"
            if dataset.description:
                desc_preview = (
                    dataset.description[:80] + "..."
                    if len(dataset.description) > 80
                    else dataset.description
                )
                response += f"\n  Description: {desc_preview}"
            response += "\n"

        response += f"\nTotal: {len(datasets)} dataset(s)"

        session.close()
        return response

    except Exception as e:
        session.close()
        logger.error(f"Error retrieving datasets for task {task_id}: {str(e)}")
        return f"Error retrieving datasets for task {task_id}: {str(e)}"


@function_tool
async def get_task_datasets(task_id: int) -> str:
    """Get all datasets associated with a specific task.

    This tool helps you look up which datasets are commonly used for a particular task.
    Use this when you encounter a task mentioned in the paper and want to see what
    datasets are already in the database for that task.

    Args:
        task_id: The ID of the task to get datasets for

    Returns:
        A formatted string with dataset information for the task, including:
        - Dataset IDs and names
        - Full names (if available)
        - Descriptions (if available)
        - Total count of datasets

    Example:
        If you see evaluation results for "Image Classification" task (ID: 1),
        call get_task_datasets(1) to see all ImageNet variants and other datasets
        commonly used for image classification.
    """
    print(f"[TOOL CALL] get_task_datasets(task_id={task_id})")
    result = get_datasets_for_task(task_id)
    print(
        f"[TOOL RESULT] {result[:200]}..."
        if len(result) > 200
        else f"[TOOL RESULT] {result}"
    )
    return result


def get_leaderboard_triples() -> List[Tuple[str, str, str, str]]:
    """Get all current leaderboards as (area, task, dataset_name, metric_name) tuples.

    This function queries the task_dataset_metrics table to get all defined leaderboards,
    which are represented as (task, dataset, metric) triples. Each leaderboard is enriched
    with the area name from the task's area relationship.

    Returns:
        List of tuples: (area_name, task_name, dataset_name, metric_name)
        Area name will be "Other" if task has no area assigned

    Example:
        [
            ("Computer Vision", "Image Classification", "ImageNet-1k", "Top-1 Accuracy"),
            ("Computer Vision", "Image Classification", "ImageNet-1k", "Top-5 Accuracy"),
            ("NLP", "Question Answering", "SQuAD", "F1"),
            ...
        ]
    """
    session: Session = db_manager.session_local()

    try:
        # Query all task-dataset-metric triples with joins to get names
        # Select the columns we need directly from the joined tables
        query = (
            session.query(
                DBArea.name.label("area_name"),
                DBTask.name.label("task_name"),
                DBDataset.name.label("dataset_name"),
                DBMetric.name.label("metric_name"),
            )
            .select_from(DBTaskDatasetMetric)
            .join(DBTask, DBTaskDatasetMetric.task_id == DBTask.id)
            .join(DBDataset, DBTaskDatasetMetric.dataset_id == DBDataset.id)
            .join(DBMetric, DBTaskDatasetMetric.metric_id == DBMetric.id)
            .join(DBArea, DBTask.area_id == DBArea.id, isouter=True)
            .order_by(
                DBArea.name.asc().nullsfirst(),
                DBTask.name.asc(),
                DBDataset.name.asc(),
                DBMetric.name.asc(),
            )
        )

        rows = query.all()

        result = []
        for row in rows:
            area_name = row.area_name if row.area_name else "Other"
            result.append((area_name, row.task_name, row.dataset_name, row.metric_name))

        session.close()
        return result

    except Exception as e:
        session.close()
        logger.error(f"Error retrieving leaderboard triples: {str(e)}")
        return []


@function_tool
async def get_leaderboard_triples_tool() -> str:
    """Get all current leaderboards as (area, task, dataset, metric) tuples.

    This tool helps you understand which leaderboards currently exist in the database.
    Use this when you want to see what evaluation results are already being tracked
    for specific combinations of tasks, datasets, and metrics.

    Returns:
        A formatted string listing all leaderboards, grouped by area, with format:
        - Area: Task | Dataset | Metric

    Example:
        If you see evaluation results in the paper, call get_leaderboard_triples()
        to check if there's already a leaderboard for that task-dataset-metric combination.
        This helps ensure you're extracting results that match existing leaderboard structures.
    """
    print("[TOOL CALL] get_leaderboard_triples_tool()")
    triples = get_leaderboard_triples()

    # Format the triples into a readable string
    if not triples:
        result = "No leaderboards found in database"
    else:
        # Group by area
        by_area = {}
        for area, task, dataset, metric in triples:
            if area not in by_area:
                by_area[area] = []
            by_area[area].append((task, dataset, metric))

        result = "CURRENT LEADERBOARDS IN DATABASE:\n"
        result += "=" * 60 + "\n\n"

        for area in sorted(by_area.keys()):
            result += f"{area}:\n"
            for task, dataset, metric in sorted(by_area[area]):
                result += f"  - {task} | {dataset} | {metric}\n"
            result += "\n"

        result += f"Total leaderboards: {len(triples)}\n"

    print(
        f"[TOOL RESULT] {result[:200]}..."
        if len(result) > 200
        else f"[TOOL RESULT] {result}"
    )
    return result


def get_dataset_details_by_id(dataset_id: int) -> str:
    """Get detailed information about a specific dataset by its ID.

    This function retrieves comprehensive details about a dataset from the database,
    including associated tasks and metadata. This is useful when you want to learn
    more about a dataset that was mentioned in get_datasets_for_task results.

    Args:
        dataset_id: The ID of the dataset to get details for

    Returns:
        Formatted string with dataset information, or error message if dataset not found
    """
    session: Session = db_manager.session_local()

    try:
        from sqlalchemy.orm import joinedload

        # Query dataset with tasks relationship loaded
        dataset = (
            session.query(DBDataset)
            .options(joinedload(DBDataset.tasks))
            .filter(DBDataset.id == dataset_id)
            .first()
        )

        if not dataset:
            session.close()
            return f"Dataset with ID {dataset_id} not found"

        # Format response with comprehensive information
        response = f"Dataset Details (ID: {dataset_id}):\n"
        response += "=" * 60 + "\n\n"

        response += f"Name: {dataset.name}\n"

        if dataset.full_name:
            response += f"Full Name: {dataset.full_name}\n"

        if dataset.slug:
            response += f"Slug: {dataset.slug}\n"

        if dataset.description:
            response += f"\nDescription:\n{dataset.description}\n"

        # URLs
        urls = []
        if dataset.url:
            urls.append(f"  - Main URL: {dataset.url}")
        if dataset.hf_url:
            urls.append(f"  - Hugging Face: {dataset.hf_url}")
        if dataset.paper_url:
            urls.append(f"  - Paper: {dataset.paper_url}")

        if urls:
            response += "\nURLs:\n" + "\n".join(urls) + "\n"

        # Associated tasks
        if dataset.tasks:
            response += f"\nAssociated Tasks ({len(dataset.tasks)}):\n"
            for task in sorted(dataset.tasks, key=lambda t: t.name):
                response += f"  - ID: {task.id:<4} - {task.name}"
                if task.area:
                    response += f" (Area: {task.area.name})"
                response += "\n"
        else:
            response += "\nAssociated Tasks: None\n"

        session.close()
        return response

    except Exception as e:
        session.close()
        logger.error(f"Error retrieving dataset details for ID {dataset_id}: {str(e)}")
        return f"Error retrieving dataset details for ID {dataset_id}: {str(e)}"


@function_tool
async def get_dataset_details(dataset_id: int) -> str:
    """Get detailed information about a specific dataset.

    This tool helps you get comprehensive details about a dataset when you have its ID.
    Use this after calling get_task_datasets to learn more about a specific dataset
    that you're interested in.

    Args:
        dataset_id: The ID of the dataset to get details for

    Returns:
        A formatted string with dataset information, including:
        - Dataset name, full name, slug
        - Description
        - URLs (main URL, Hugging Face URL, paper URL)
        - Associated tasks
        - Total count of associated tasks

    Example:
        If get_task_datasets returns a list including "ID: 42 - COCO val2017",
        call get_dataset_details(42) to get more information about that dataset,
        including its full description, URLs, and what other tasks it's used for.
    """
    print(f"[TOOL CALL] get_dataset_details(dataset_id={dataset_id})")
    result = get_dataset_details_by_id(dataset_id)
    print(
        f"[TOOL RESULT] {result[:200]}..."
        if len(result) > 200
        else f"[TOOL RESULT] {result}"
    )
    return result


# ============================================================================
# Dataset Search and Management Tools
# ============================================================================


@function_tool
async def find_dataset(
    dataset_name: str | None = None,
    arxiv_id: str | None = None,
    hf_url: str | None = None,
) -> str:
    """Find a dataset in the database by name, ArXiv ID, or Hugging Face URL.

    This tool supports case-insensitive partial matching. You should call this tool multiple times
    with different search strategies to thoroughly check for existing datasets before concluding
    that a dataset is not found.

    Args:
        dataset_name: The name of the dataset to find (case-insensitive partial matching).
                     Searches in name, full_name, and description fields.
        arxiv_id: The ArXiv ID of the paper that introduced the dataset (e.g., "2103.00020").
                 This searches for datasets where the introducing paper has this ArXiv ID.
                 Version numbers are automatically ignored (e.g., "2103.00020v2" matches "2103.00020").
        hf_url: The Hugging Face URL of the dataset (partial matching supported).
               Can be full URL or partial (e.g., "huggingface.co/datasets/imagenet-1k").

    Returns:
        A JSON string with dataset information if found, or "Dataset not found" if not found.

    Important:
        - At least one of dataset_name, arxiv_id, or hf_url must be provided.
        - If multiple parameters are provided, they are combined with AND logic.
        - Call this tool multiple times with different search strategies to ensure thorough searching.
        - Try searching by ArXiv ID first (most reliable), then HF URL, then dataset name with variations.
    """
    # Log tool call for debugging
    search_params = []
    if dataset_name:
        search_params.append(f"dataset_name='{dataset_name}'")
    if arxiv_id:
        search_params.append(f"arxiv_id='{arxiv_id}'")
    if hf_url:
        search_params.append(f"hf_url='{hf_url}'")
    print(f"[TOOL CALL] find_dataset({', '.join(search_params)})")

    if not dataset_name and not arxiv_id and not hf_url:
        return "Error: At least one search parameter (dataset_name, arxiv_id, or hf_url) must be provided"

    session: Session = db_manager.session_local()

    from sqlalchemy import and_, or_, select

    try:
        # Build query with filters
        query = session.query(DBDataset)
        filters = []

        # Search by ArXiv ID (of the introducing paper)
        if arxiv_id:
            # Normalize arxiv_id (remove version if present)
            arxiv_base = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

            # Find papers with matching ArXiv ID
            paper_subquery = (
                select(DBPaper.id)
                .filter(DBPaper.arxiv_id.like(f"{arxiv_base}%"))
                .scalar_subquery()
            )

            filters.append(DBDataset.introducing_paper_id.in_(paper_subquery))

        # Search by Hugging Face URL
        if hf_url:
            # Support partial matching for HF URLs
            filters.append(DBDataset.hf_url.ilike(f"%{hf_url}%"))

        # Search by dataset name
        if dataset_name:
            # Try direct search first
            name_filters = or_(
                DBDataset.name.ilike(f"%{dataset_name}%"),
                DBDataset.full_name.ilike(f"%{dataset_name}%"),
                DBDataset.description.ilike(f"%{dataset_name}%"),
            )
            filters.append(name_filters)

        # Apply all filters
        if filters:
            query = query.filter(and_(*filters))

        # Prioritize exact matches and base datasets (no parent)
        # First try exact name match (case-insensitive)
        if dataset_name:
            exact_match = query.filter(DBDataset.name.ilike(dataset_name)).first()
            if exact_match:
                db_dataset = exact_match
            else:
                # Try to prioritize base datasets (no parent_dataset_id) and shorter names
                # Order by: parent_dataset_id NULL first (base datasets), then by name alphabetically
                db_dataset = query.order_by(
                    DBDataset.parent_dataset_id.asc().nullsfirst(),
                    DBDataset.name.asc(),
                ).first()
        else:
            # Execute query without name priority
            db_dataset = query.first()

        if not db_dataset:
            session.close()
            result = "Dataset not found"
            print(f"[TOOL RESULT] {result}")
            return result

        # Format response with key information
        response = f"Found dataset: ID={db_dataset.id}, Name={db_dataset.name}, Slug={db_dataset.slug}"
        if db_dataset.full_name:
            response += f", Full Name={db_dataset.full_name}"
        if db_dataset.description:
            desc_preview = (
                db_dataset.description[:100] + "..."
                if len(db_dataset.description) > 100
                else db_dataset.description
            )
            response += f", Description={desc_preview}"
        if db_dataset.hf_url:
            response += f", HF URL={db_dataset.hf_url}"
        if db_dataset.paper_url:
            response += f", Paper URL={db_dataset.paper_url}"

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except Exception as e:
        session.close()
        error_msg = f"Error searching for dataset: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg


@function_tool
async def get_available_tasks() -> str:
    """Get a list of all available tasks in the database that datasets can be linked to.

    Returns:
        A formatted list of all available tasks with their IDs, names, and areas.
    """
    session: Session = db_manager.session_local()

    try:
        tasks = session.query(DBTask).order_by(DBTask.id).all()

        if not tasks:
            session.close()
            return "No tasks found in database"

        # Group tasks by area
        tasks_by_area = {}
        for task in tasks:
            area_name = task.area.name if task.area else "Other"
            if area_name not in tasks_by_area:
                tasks_by_area[area_name] = []
            tasks_by_area[area_name].append((task.id, task.name))

        # Format response
        response = "Available Tasks in Database:\n" + "=" * 60 + "\n\n"
        for area_name in sorted(tasks_by_area.keys()):
            response += f"{area_name}:\n"
            for task_id, task_name in tasks_by_area[area_name]:
                response += f"  - ID: {task_id:<4} - {task_name}\n"
            response += "\n"

        response += "=" * 60
        response += f"\nTotal Tasks: {len(tasks)}"

        session.close()
        return response

    except Exception as e:
        session.close()
        return f"Error retrieving tasks: {str(e)}"


@function_tool
async def add_dataset(
    name: str,
    description: str,
    task_ids: list[int],
    full_name: str | None = None,
    url: str | None = None,
    hf_url: str | None = None,
    paper_url: str | None = None,
) -> str:
    """Add a new dataset to the database and link it to one or more tasks.

    IMPORTANT: Every dataset must be linked to at least one task. Use get_available_tasks() to see all available tasks.

    Args:
        name: The name of the dataset (required). E.g., "COCO", "ImageNet", "SpeechCommands"
        description: A description of the dataset (required). Should explain what the dataset contains and its purpose.
        task_ids: List of task IDs this dataset is used for (required). MUST contain at least one valid task ID.
                 E.g., [1] for Image Classification, [2] for Object Detection, [1, 19] for multiple tasks.
                 Use get_available_tasks() to see all available task IDs.
        full_name: The full name of the dataset (optional). E.g., "Common Objects in Context" for COCO.
        url: The main URL for the dataset (optional). E.g., official website or documentation.
        hf_url: Hugging Face dataset URL (optional). E.g., "https://huggingface.co/datasets/..."
        paper_url: URL to the paper that introduced this dataset (optional). E.g., ArXiv URL.

    Returns:
        A success message with the created dataset details, or an error message if creation failed.
    """
    session: Session = db_manager.session_local()
    service = DatasetService(session)

    try:
        # Validate task_ids is not empty
        if not task_ids or len(task_ids) == 0:
            session.close()
            return "✗ Failed to create dataset: task_ids cannot be empty. Every dataset must be linked to at least one task. Use get_available_tasks() to see available tasks."

        # Create the dataset request
        dataset_request = DatasetCreateRequest(
            name=name,
            description=description,
            task_ids=task_ids,
            full_name=full_name,
            url=url,
            hf_url=hf_url,
            paper_url=paper_url,
        )

        # Add the dataset using the service
        dataset = service.create_dataset(dataset_request)

        # Format success response
        response = f"✓ Successfully created dataset: ID={dataset.id}, Name={dataset.name}, Slug={dataset.slug}"
        if dataset.full_name:
            response += f", Full Name={dataset.full_name}"
        response += f", Linked to Task IDs={task_ids}"
        if hf_url:
            response += f", Hugging Face URL={hf_url}"

        session.close()
        return response

    except ValueError as e:
        session.close()
        error_msg = str(e)
        if "Task IDs not found" in error_msg:
            return f"✗ Failed to create dataset: {error_msg}. Use get_available_tasks() to see valid task IDs."
        return f"✗ Failed to create dataset: {error_msg}"
    except Exception as e:
        session.close()
        return f"✗ Failed to create dataset: {str(e)}"


# ============================================================================
# Evaluation Management Tools
# ============================================================================


@function_tool
async def get_leaderboard_metrics(task_id: int, dataset_id: int) -> str:
    """Get the list of allowed metrics for a specific leaderboard (task + dataset).

    This tool helps you determine which metrics are valid for a given (task, dataset) pair.
    Each (task, dataset, metric) triple defines a unique leaderboard.

    Args:
        task_id: The ID of the task
        dataset_id: The ID of the dataset

    Returns:
        A formatted string with the allowed metrics for this leaderboard, including their directions (higher/lower is better).
        If no metrics are configured, returns a message indicating all metrics are allowed (backwards compatibility).
    """
    session: Session = db_manager.session_local()
    service = LeaderboardMetricService(session)

    try:
        result = service.get_leaderboard_metrics(task_id, dataset_id)

        if not result["metrics"]:
            response = (
                f"No specific metrics configured for leaderboard (Task {task_id}, Dataset {dataset_id}). "
                f"All metrics are allowed (backwards compatibility mode)."
            )
        else:
            response = f"Allowed metrics for leaderboard (Task {result['task_name']}, Dataset {result['dataset_name']}):\n"
            for metric in result["metrics"]:
                direction = (
                    "higher is better"
                    if metric["metric_direction"] == "higher_is_better"
                    else "lower is better"
                )
                response += f"  - {metric['metric_name']} ({direction})\n"

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except ValueError as e:
        session.close()
        error_msg = f"Error: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg
    except Exception as e:
        session.close()
        error_msg = f"Error retrieving leaderboard metrics: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg


@function_tool
async def add_evaluation_result(
    paper_id: int,
    task_id: int,
    dataset_id: int,
    metrics: str,
    best_metric: str,
    model_name: Optional[str] = None,
    methodology: Optional[str] = None,
    uses_additional_data: bool = False,
    evaluated_on: Optional[str] = None,
    external_source_url: Optional[str] = None,
) -> str:
    """Add a new evaluation result to the database.

    This tool adds an evaluation result to a specific leaderboard triple (task, dataset, metric).
    The evaluation will be automatically ranked on the leaderboard defined by (task_id, dataset_id, best_metric).

    Args:
        paper_id: The ID of the paper that produced this evaluation
        task_id: The ID of the task being evaluated
        dataset_id: The ID of the dataset used for evaluation
        metrics: JSON string with dictionary of metric names to values (e.g., '{"AP": "44.9", "AP50": "64.7"}')
        best_metric: The name of the best performing metric (must be in the metrics dict)
        model_name: Name of the model/method (optional)
        methodology: Description of the methodology (optional)
        uses_additional_data: Whether additional data was used beyond the dataset (default: False)
        evaluated_on: Date when evaluation was performed in YYYY-MM-DD format (optional)
        external_source_url: URL to external source like a competition (optional)

    Returns:
        A success message with evaluation details, or an error message if creation failed.
    """
    # Parse metrics JSON string
    try:
        metrics_dict = json.loads(metrics)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON format for metrics parameter: {str(e)}"

    # Log tool call for debugging
    print(
        f"[TOOL CALL] add_evaluation_result(paper_id={paper_id}, task_id={task_id}, "
        f"dataset_id={dataset_id}, metrics={metrics_dict}, best_metric={best_metric}, "
        f"model_name={model_name})"
    )

    session: Session = db_manager.session_local()

    try:
        # 1. Check if paper exists
        paper = session.query(DBPaper).filter(DBPaper.id == paper_id).first()
        if not paper:
            session.close()
            return f"Error: Paper with ID {paper_id} not found in database"

        # 2. Validate and normalize best_metric
        # First, check if best_metric is in the metrics dict
        metric_keys = list(metrics_dict.keys())
        best_metric_lower = best_metric.lower()

        # Find matching metric in database (case-insensitive)
        metric_def = (
            session.query(DBMetric).filter(DBMetric.name.ilike(best_metric)).first()
        )
        if not metric_def:
            session.close()
            return (
                f"Error: Metric '{best_metric}' not found in metrics table. "
                f"Available metrics in evaluation: {', '.join(metric_keys)}. "
                f"Please ensure the metric name is correct and exists in the database."
            )

        # Use the canonical name from the database
        normalized_best_metric = metric_def.name

        # Verify best_metric is in the metrics dict (case-insensitive)
        if not any(key.lower() == best_metric_lower for key in metric_keys):
            session.close()
            return (
                f"Error: best_metric '{best_metric}' must be one of the metrics in the metrics dictionary. "
                f"Available metrics: {', '.join(metric_keys)}"
            )

        # 3. Check for duplicates (including best_metric in the key)
        existing = (
            session.query(DBEvaluation)
            .filter(
                DBEvaluation.paper_id == paper_id,
                DBEvaluation.task_id == task_id,
                DBEvaluation.dataset_id == dataset_id,
                DBEvaluation.model_name == model_name,
                DBEvaluation.best_metric == normalized_best_metric,
            )
            .first()
        )

        if existing:
            session.close()
            return (
                f"Evaluation already exists: ID={existing.id}, Paper ID={paper_id}, "
                f"Task ID={task_id}, Dataset ID={dataset_id}, Model='{model_name}', "
                f"Best Metric='{normalized_best_metric}'. "
                f"Duplicates are not allowed for the same (paper, task, dataset, model, best_metric) combination."
            )

        # 4. Validate all metrics exist in database
        metric_names_to_check = list(metrics_dict.keys())
        invalid_metrics = []
        for metric_name in metric_names_to_check:
            metric_check = (
                session.query(DBMetric).filter(DBMetric.name.ilike(metric_name)).first()
            )
            if not metric_check:
                invalid_metrics.append(metric_name)

        if invalid_metrics:
            session.close()
            return (
                f"Error: The following metrics are not found in the metrics table: {', '.join(invalid_metrics)}. "
                f"Please ensure all metric names are correct and exist in the database."
            )

        # 5. Normalize metric names in the metrics dict to canonical form
        normalized_metrics = {}
        for metric_key, metric_value in metrics_dict.items():
            metric_def = (
                session.query(DBMetric).filter(DBMetric.name.ilike(metric_key)).first()
            )
            if metric_def:
                normalized_metrics[metric_def.name] = metric_value
            else:
                # This shouldn't happen due to validation above, but handle it gracefully
                normalized_metrics[metric_key] = metric_value

        # 6. Add the evaluation using the service layer
        evaluation_service = EvaluationService(session)
        evaluation = evaluation_service.create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            metrics=normalized_metrics,
            model_name=model_name,
            methodology=methodology,
            uses_additional_data=uses_additional_data,
            best_metric=normalized_best_metric,
            evaluated_on=evaluated_on,
            external_source_url=external_source_url,
        )

        # Format success response
        response = (
            f"✓ Successfully created evaluation: ID={evaluation.id}, Paper ID={paper_id}, "
            f"Task ID={task_id}, Dataset ID={dataset_id}, Model='{model_name}', "
            f"Metrics={normalized_metrics}, Best Metric='{normalized_best_metric}', "
            f"Best Rank={evaluation.best_rank}"
        )

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except ValueError as e:
        session.close()
        error_msg = f"Validation error: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg
    except Exception as e:
        session.close()
        error_msg = f"Error creating evaluation: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg
