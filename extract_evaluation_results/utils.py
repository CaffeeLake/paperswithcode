"""
Utility functions for the evaluation extraction pipeline.

This module consolidates common helper functions used across multiple steps to avoid duplication.
Agent tools (@function_tool) have been moved to tools.py.

To test a function, you can run:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/utils.py
```
"""

import logging
from typing import List, Tuple

from backend.database.connection import db_manager
from backend.utils.paper_utils import get_title, get_authors, get_abstract
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def get_paper_details(arxiv_id: str) -> str:
    """Get formatted paper details including title, authors, and abstract.

    This function consolidates the get_paper_details function that was duplicated
    across step_2.py, step_3.py, and step_4.py.

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        Formatted string with paper title, authors, ArXiv ID, and abstract
    """
    paper_title = await get_title(arxiv_id)
    paper_authors = await get_authors(arxiv_id)
    paper_abstract = await get_abstract(arxiv_id)

    return f"""
### Arxiv ID: {arxiv_id}
### Title: {paper_title}

### Authors:
{paper_authors}

### Abstract
{paper_abstract}
"""


def get_formatted_tasks_list() -> str:
    """Get a formatted list of all available tasks from the database, grouped by area.

    This function fetches tasks dynamically from the database instead of using hardcoded lists.
    For each task, it also includes a list of datasets currently linked to that task,
    providing context about the current information landscape of the PapersWithCode app.

    Returns:
        Formatted string with tasks grouped by area, including associated datasets,
        suitable for inclusion in agent prompts
    """
    session: Session = db_manager.session_local()

    try:
        from backend.models.database import (
            Task as DBTask,
            Area as DBArea,
            Dataset as DBDataset,
            TaskDatasetMetric as DBTaskDatasetMetric,
        )
        from sqlalchemy import distinct

        # Query all tasks with their areas, ordered by area name and task ID
        tasks = (
            session.query(DBTask)
            .join(DBArea, DBTask.area_id == DBArea.id, isouter=True)
            .order_by(DBArea.name.asc().nullsfirst(), DBTask.id.asc())
            .all()
        )

        if not tasks:
            session.close()
            return "No tasks found in database"

        # Group tasks by area with their datasets
        tasks_by_area = {}
        total_datasets = 0
        # Track all tasks with their dataset counts for top 5 ranking
        tasks_with_counts = []

        for task in tasks:
            area_name = task.area.name if task.area else "Other"
            if area_name not in tasks_by_area:
                tasks_by_area[area_name] = []

            # Get dataset names for this task through task_dataset_metrics
            dataset_query = (
                session.query(distinct(DBDataset.name))
                .join(
                    DBTaskDatasetMetric, DBDataset.id == DBTaskDatasetMetric.dataset_id
                )
                .filter(DBTaskDatasetMetric.task_id == task.id)
                .order_by(DBDataset.name)
            )
            dataset_names = [row[0] for row in dataset_query.all()]
            dataset_count = len(dataset_names)
            total_datasets += dataset_count

            tasks_by_area[area_name].append((task.id, task.name, dataset_names))
            # Store task info with dataset count for ranking
            tasks_with_counts.append((task.id, task.name, area_name, dataset_count))

        # Format response as proper Markdown
        response = "## Available tasks in the database, by area:\n\n"

        for area_name in sorted(tasks_by_area.keys()):
            # Use ### for area headings
            response += f"### {area_name}\n\n"

            for task_id, task_name, dataset_names in tasks_by_area[area_name]:
                # Task as main list item
                response += f"- **ID: {task_id}** - {task_name}\n"

                # Add datasets as a single sub-bullet point
                if dataset_names:
                    # Limit to first 5 datasets to keep output manageable
                    if len(dataset_names) <= 5:
                        datasets_str = ", ".join(dataset_names)
                    else:
                        datasets_str = (
                            ", ".join(dataset_names[:5])
                            + f" (+{len(dataset_names) - 5} more)"
                        )
                    response += f"  - Datasets: {datasets_str}\n"
                else:
                    response += "  - Datasets: *None*\n"

            response += "\n"

        # Summary section as Markdown
        response += "---\n\n"
        response += f"**Total Areas:** {len(tasks_by_area)}\n\n"
        response += f"**Total Tasks:** {len(tasks)}\n\n"
        response += f"**Total Dataset-Task Links:** {total_datasets}\n\n"

        # Top 5 tasks with most datasets
        top_tasks = sorted(tasks_with_counts, key=lambda x: x[3], reverse=True)[:5]
        if top_tasks:
            response += "### Top 5 Tasks by Dataset Count\n\n"
            response += "| Rank | Task ID | Task Name | Area | Dataset Count |\n"
            response += "|------|---------|-----------|------|---------------|\n"
            for rank, (task_id, task_name, area_name, dataset_count) in enumerate(
                top_tasks, 1
            ):
                response += f"| {rank} | {task_id} | {task_name} | {area_name} | {dataset_count} |\n"
            response += "\n"

        response += "*Note: This shows datasets currently linked to each task. "
        response += "When adding a new dataset, link it to the appropriate task(s) based on its purpose.*"

        session.close()
        return response

    except Exception as e:
        session.close()
        logger.error(f"Error retrieving tasks: {str(e)}")
        return f"Error retrieving tasks: {str(e)}"


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
        from backend.models.database import Task as DBTask

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
        from backend.models.database import (
            TaskDatasetMetric as DBTaskDatasetMetric,
            Task as DBTask,
            Dataset as DBDataset,
            Metric as DBMetric,
            Area as DBArea,
        )

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
        from backend.models.database import Dataset as DBDataset
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


def find_dataset_sync(
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

    from backend.models.database import Dataset as DBDataset, Paper as DBPaper
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


if __name__ == "__main__":
    print(get_formatted_tasks_list())
    print("\n" + "=" * 60 + "\n")
    # print("CURRENT LEADERBOARDS:")
    # print("=" * 60 + "\n")
    # triples = get_leaderboard_triples()
    # for area, task, dataset, metric in triples:
    #     print(f"{area} | {task} | {dataset} | {metric}")
    # print(f"\nTotal leaderboards: {len(triples)}")
    import asyncio

    result = asyncio.run(get_paper_details("2103.00020"))
    print(result)
