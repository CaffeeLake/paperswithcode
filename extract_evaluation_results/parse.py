"""
Main script that orchestrates the evaluation result extraction pipeline (agentic workflow).

This script:
1. Runs step_1 to extract evaluation results from a paper PDF
2. Runs step_2 for each dataset mentioned in the results to find whether it is already in the database or not (in parallel)
3. Runs step_3 for datasets not found in step_2 to gather additional information from the web and Hugging Face
4. Runs step_4 for datasets gathered in step_3 to add them to the database
5. Runs step_5 to normalize evaluation results datasets using outputs from step_2 and step_4
6. Optionally runs step_6 to align evaluation results with database IDs and add them to the database

You can run it like so:

```bash
# Run all steps (including step 4, 5, and 6)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545

# Run only steps 1, 2, 3, 4, and 5 (skip step 6 - no database insertion)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --skip-step-6

# Run only steps 1, 2, and 3 (skip step 4, 5, and 6 - no database additions)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --skip-addition
```

Note: Step 5 normalizes evaluation results datasets. Step 6 only processes papers whose evaluation results are from datasets
that are already present in the database (or were just added in step 4).
"""

import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

from backend.database.connection import db_manager
from backend.services.paper_service import PaperService
from backend.services.dataset_service import DatasetService

from extract_evaluation_results.step_1 import step_1
from extract_evaluation_results.step_2 import (
    step_2,
    extract_dataset_id,
    parse_dataset_info,
)
from extract_evaluation_results.step_3 import step_3
from extract_evaluation_results.utils import get_paper_details

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration
MAX_CONCURRENT_REQUESTS = 2
DELAY_BETWEEN_STARTS = 2.0
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5.0


# Cache helper functions
def get_cache_dir(arxiv_id: str) -> Path:
    """Get the cache directory for a given arxiv_id."""
    cache_dir = Path("backend/outputs/evaluation_results") / arxiv_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def read_json_if_exists(path: Path) -> Optional[Union[dict, list]]:
    """Read JSON from path if it exists, otherwise return None."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read cache file {path}: {e}")
            return None
    return None


def write_json(path: Path, data: Union[dict, list]) -> None:
    """Write data as JSON to path."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def write_text(path: Path, text: str) -> None:
    """Write text to path."""
    path.write_text(text)


async def step_2_with_retry(
    arxiv_id: str,
    dataset_detail: dict,
    evaluation_results: list,
    paper_details: str,
    use_web_search: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, Union[str, Exception]]:
    """Run step_2 with rate limiting and retry logic."""
    async with semaphore:
        dataset_name = dataset_detail.get("dataset_name", "Unknown")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Processing dataset '{dataset_name}' (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                result = await step_2(
                    arxiv_id=arxiv_id,
                    dataset_detail=dataset_detail,
                    evaluation_results=evaluation_results,
                    paper_details=paper_details,
                    use_web_search=use_web_search,
                )
                return (dataset_detail, result)

            except Exception as e:
                import traceback

                error_str = str(e)
                error_type = type(e).__name__
                error_traceback = traceback.format_exc()

                # Log full error details for debugging
                logger.error(
                    f"Error processing dataset '{dataset_name}': {error_type}: {error_str}"
                )
                logger.debug(f"Full traceback:\n{error_traceback}")

                is_rate_limit = (
                    "429" in error_str
                    or "rate_limit" in error_str.lower()
                    or "Rate limit" in error_str
                )

                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BASE_DELAY * (2**attempt)
                    wait_match = re.search(r"Please try again in ([\d.]+)s", error_str)
                    if wait_match:
                        wait_time = float(wait_match.group(1)) + 1.0

                    logger.warning(
                        f"Rate limit hit for dataset '{dataset_name}'. Retrying in {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Create a more informative error message
                    error_msg = f"{error_type}: {error_str}"
                    logger.error(
                        f"Failed to process dataset '{dataset_name}': {error_msg}"
                    )
                    return (dataset_detail, Exception(error_msg))

        return (dataset_detail, Exception(f"Failed after {MAX_RETRIES} attempts"))


def align_evaluation_results(
    arxiv_id: str,
    evaluation_results: list,
    step_2_results: list,
    step_4_results: Optional[list] = None,
) -> tuple[list, str]:
    """Align evaluation results with database IDs (paper_id, task_id, dataset_id).

    Args:
        arxiv_id: ArXiv ID of the paper
        evaluation_results: List of evaluation results from step_1
        step_2_results: List of step_2 results (datasets found in database)
        step_4_results: List of step_4 results (datasets newly added to database)
    """
    session = db_manager.session_local()

    # Get paper_id
    paper_service = PaperService(session)
    paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
    paper_id = paper.id

    # Build dataset_name -> dataset_id mapping
    dataset_name_to_id = {}
    dataset_service = DatasetService(session)

    # Add datasets from step_2 (already in database)
    for step_2_result in step_2_results:
        if not step_2_result.get("success"):
            continue

        dataset_id = extract_dataset_id(step_2_result.get("result", ""))
        if dataset_id:
            dataset_name = step_2_result["dataset"].get("dataset_name", "")
            dataset_name_to_id[dataset_name.lower()] = dataset_id
            logger.info(f"Mapped dataset '{dataset_name}' to ID {dataset_id}")

    # Add datasets from step_4 (newly added to database)
    if step_4_results:
        for step_4_result in step_4_results:
            if not step_4_result.get("success"):
                continue

            result_text = str(step_4_result.get("result", ""))
            # Extract dataset ID from step_4 result
            # Format: "✓ Successfully created dataset: ID=X, Name=Y, Slug=Z"
            dataset_id = extract_dataset_id(result_text)
            if dataset_id:
                dataset_name = step_4_result["dataset"].get("dataset_name", "")
                dataset_name_to_id[dataset_name.lower()] = dataset_id
                logger.info(
                    f"Mapped newly added dataset '{dataset_name}' to ID {dataset_id}"
                )

    if not dataset_name_to_id:
        session.close()
        return [], "No datasets found in database. Cannot align evaluation results."

    # Group evaluation results by (model_name, dataset_name)
    grouped_results = {}
    for eval_result in evaluation_results:
        model_name = eval_result.get("model_name", "")
        dataset_name = eval_result.get("dataset_name", "")
        metric_name = eval_result.get("metric_name", "")
        metric_value = eval_result.get("metric_value", "")

        if not dataset_name:
            continue

        dataset_id = dataset_name_to_id.get(dataset_name.lower())
        if not dataset_id:
            logger.warning(
                f"Skipping evaluation result for dataset '{dataset_name}' (not found in database)"
            )
            continue

        key = (model_name, dataset_name.lower())
        if key not in grouped_results:
            grouped_results[key] = {
                "model_name": model_name,
                "dataset_name": dataset_name,
                "dataset_id": dataset_id,
                "metrics": {},
            }
        grouped_results[key]["metrics"][metric_name] = metric_value

    # Create aligned evaluation results
    aligned_results = []
    for (model_name, dataset_name_lower), group_data in grouped_results.items():
        dataset_id = group_data["dataset_id"]
        metrics = group_data["metrics"]

        if not metrics:
            continue

        task_ids = dataset_service.get_dataset_tasks(dataset_id)
        if not task_ids:
            logger.warning(
                f"Dataset {dataset_id} has no tasks linked. Skipping evaluation result."
            )
            continue

        aligned_results.append(
            {
                "paper_id": paper_id,
                "task_id": task_ids[0],  # Use first task if multiple
                "dataset_id": dataset_id,
                "metrics": metrics,
                "best_metric": list(metrics.keys())[
                    0
                ],  # Use first metric as best_metric
                "model_name": model_name if model_name else None,
            }
        )

    session.close()

    if not aligned_results:
        return [], "No evaluation results could be aligned with datasets in database."

    logger.info(f"Aligned {len(aligned_results)} evaluation results with database IDs")
    return aligned_results, ""


async def step_3_with_retry(
    dataset_detail: dict,
    arxiv_id: str,
    paper_title: Optional[str],
    semaphore: asyncio.Semaphore,
) -> tuple[dict, Union[Optional[dict], Exception]]:
    """Run step_3 with rate limiting and retry logic."""
    async with semaphore:
        dataset_name = dataset_detail.get("dataset_name", "Unknown")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Gathering info for dataset '{dataset_name}' (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                result = await step_3(
                    dataset_name=dataset_detail.get("dataset_name"),
                    arxiv_id=dataset_detail.get("paper_arxiv_id") or arxiv_id,
                    hf_url=None,
                    dataset_info=dataset_detail.get("dataset_info"),
                    paper_title=paper_title,
                )
                return (dataset_detail, result)

            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "429" in error_str
                    or "rate_limit" in error_str.lower()
                    or "Rate limit" in error_str
                )

                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BASE_DELAY * (2**attempt)
                    wait_match = re.search(r"Please try again in ([\d.]+)s", error_str)
                    if wait_match:
                        wait_time = float(wait_match.group(1)) + 1.0

                    logger.warning(
                        f"Rate limit hit for dataset '{dataset_name}'. Retrying in {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"Error gathering info for dataset '{dataset_name}': {error_str}"
                    )
                    return (dataset_detail, e)

        return (dataset_detail, Exception(f"Failed after {MAX_RETRIES} attempts"))


async def step_4_with_retry(
    dataset_detail: dict,
    step_3_result: dict,
    arxiv_id: str,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, Union[str, Exception]]:
    """Run step_4 with rate limiting and retry logic to add dataset to database."""
    # Import step_4 only when needed (lazy import)
    from extract_evaluation_results.step_4 import step_4

    async with semaphore:
        dataset_name = dataset_detail.get("dataset_name", "Unknown")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Adding dataset '{dataset_name}' to database (attempt {attempt + 1}/{MAX_RETRIES})"
                )

                # Build dataset details JSON for step_4
                # Merge original dataset_detail with step_3 result
                # Note: task_ids will be determined by the agent based on paper context
                dataset_details_for_step_4 = {
                    "name": dataset_detail.get("dataset_name"),
                    "description": step_3_result.get("description", ""),
                    "full_name": step_3_result.get("full_name"),
                    "hf_url": step_3_result.get("hf_url"),
                    "url": step_3_result.get("conference_url"),
                    "paper_url": f"https://arxiv.org/abs/{step_3_result.get('arxiv_id')}"
                    if step_3_result.get("arxiv_id")
                    else None,
                    "paper_arxiv_id": step_3_result.get("arxiv_id")
                    or dataset_detail.get("paper_arxiv_id")
                    or arxiv_id,
                }

                # Remove None values
                dataset_details_for_step_4 = {
                    k: v for k, v in dataset_details_for_step_4.items() if v is not None
                }

                # Ensure description is not empty (required field)
                if not dataset_details_for_step_4.get("description"):
                    dataset_details_for_step_4["description"] = (
                        dataset_detail.get("dataset_info", "")
                        or f"Dataset mentioned in paper {arxiv_id}"
                    )

                result = await step_4(json.dumps(dataset_details_for_step_4))
                return (dataset_detail, result)

            except Exception as e:
                error_str = str(e)
                is_rate_limit = (
                    "429" in error_str
                    or "rate_limit" in error_str.lower()
                    or "Rate limit" in error_str
                )

                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BASE_DELAY * (2**attempt)
                    wait_match = re.search(r"Please try again in ([\d.]+)s", error_str)
                    if wait_match:
                        wait_time = float(wait_match.group(1)) + 1.0

                    logger.warning(
                        f"Rate limit hit for dataset '{dataset_name}'. Retrying in {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"Error adding dataset '{dataset_name}' to database: {error_str}"
                    )
                    return (dataset_detail, e)

        return (dataset_detail, Exception(f"Failed after {MAX_RETRIES} attempts"))


async def run_step_6(
    arxiv_id: str,
    evaluation_results: list,
    step_2_results: list,
    step_4_results: Optional[list] = None,
) -> tuple[list, Optional[str], Optional[str]]:
    """Run step 6 to add evaluation results to database.

    Returns:
        Tuple of (aligned_results, step_6_result, error_message)
    """
    # Check if we have datasets in database (from step_2 or step_4)
    has_datasets = any(
        r.get("success") and extract_dataset_id(str(r.get("result", ""))) is not None
        for r in step_2_results
    ) or (
        step_4_results
        and any(
            r.get("success")
            and extract_dataset_id(str(r.get("result", ""))) is not None
            for r in step_4_results
        )
    )

    if not evaluation_results or not has_datasets:
        logger.info(
            "Skipping Step 6: No evaluation results or no datasets found in database"
        )
        return [], None, None

    logger.info("=" * 60)
    logger.info("STEP 6: Aligning evaluation results and adding to database")
    logger.info("=" * 60)

    aligned_results, alignment_error = align_evaluation_results(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
        step_4_results=step_4_results or [],
    )

    if alignment_error:
        logger.error(f"Alignment failed: {alignment_error}")
        return [], None, alignment_error

    if not aligned_results:
        logger.warning("No evaluation results to add to database")
        return [], None, None

    # Import step_6 only when needed (lazy import)
    from extract_evaluation_results.step_6 import step_6

    paper_details = await get_paper_details(arxiv_id)
    step_6_result = await step_6(
        arxiv_id=arxiv_id,
        aligned_evaluation_results=aligned_results,
        paper_details=paper_details,
    )
    logger.info(
        f"Step 6 completed: {step_6_result[:200] if step_6_result else 'No result'}..."
    )
    return aligned_results, step_6_result, None


async def run_pipeline(
    arxiv_id: str,
    skip_step_6: bool = False,
    skip_addition: bool = False,
    resume: bool = False,
) -> dict:
    """Run the complete evaluation extraction pipeline."""
    logger.info(f"Starting pipeline for paper: {arxiv_id}")
    if resume:
        logger.info("Resume mode enabled: will use cached results when available")

    cache_dir = get_cache_dir(arxiv_id)

    # Step 1: Extract evaluation results
    logger.info("=" * 60)
    logger.info("STEP 1: Extracting evaluation results from paper")
    logger.info("=" * 60)

    step_1_data = None
    step_1_path = cache_dir / "step_1.json"

    if resume:
        step_1_data = read_json_if_exists(step_1_path)
        if step_1_data:
            logger.info("Using cached Step 1 results")

    if not step_1_data:
        step_1_response = await step_1(arxiv_id)
        if step_1_response is None:
            return {
                "success": False,
                "error": "Step 1 failed: Could not extract evaluation results",
                "step_1_response": None,
                "step_2_results": [],
            }

        step_1_data = json.loads(step_1_response)
        write_json(step_1_path, step_1_data)
        logger.info("Step 1 results cached")

    evaluation_results = step_1_data.get("evaluation_results", [])
    dataset_details = step_1_data.get("dataset_details", [])

    logger.info(f"Step 1 completed: Found {len(evaluation_results)} evaluation results")
    logger.info(f"Found {len(dataset_details)} datasets mentioned in the paper")

    if not dataset_details:
        return {
            "success": True,
            "step_1_response": step_1_data,
            "step_2_results": [],
            "message": "No datasets found to process",
        }

    # Step 2: Process datasets
    logger.info("=" * 60)
    logger.info(f"STEP 2: Processing {len(dataset_details)} datasets")
    logger.info(
        f"Using rate limiting: max {MAX_CONCURRENT_REQUESTS} concurrent requests"
    )
    logger.info("=" * 60)

    step_2_path = cache_dir / "step_2_results.json"
    results = None

    if resume:
        results = read_json_if_exists(step_2_path)
        if results:
            logger.info(f"Using cached Step 2 results ({len(results)} datasets)")

    if not results:
        paper_details = await get_paper_details(arxiv_id)
        use_web_search = bool(os.getenv("EXA_API_KEY"))
        if not use_web_search:
            logger.warning(
                "EXA_API_KEY not found. Web search disabled for dataset finding."
            )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        tasks = []

        for idx, dataset_detail in enumerate(dataset_details):
            dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")
            logger.info(
                f"Queuing dataset {idx + 1}/{len(dataset_details)}: {dataset_name}"
            )

            task = step_2_with_retry(
                arxiv_id=arxiv_id,
                dataset_detail=dataset_detail,
                evaluation_results=evaluation_results,
                paper_details=paper_details,
                use_web_search=use_web_search,
                semaphore=semaphore,
            )
            tasks.append(task)

            if idx < len(dataset_details) - 1:
                await asyncio.sleep(DELAY_BETWEEN_STARTS)

        logger.info(
            f"Running {len(tasks)} dataset processing tasks with rate limiting..."
        )
        step_2_results = await asyncio.gather(*tasks, return_exceptions=False)

        # Process step_2 results
        results = []
        for idx, (dataset_detail, result) in enumerate(step_2_results):
            dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")

            if isinstance(result, Exception):
                logger.error(f"Error processing dataset {dataset_name}: {result}")
                results.append(
                    {
                        "dataset": dataset_detail,
                        "success": False,
                        "error": str(result),
                        "result": None,
                    }
                )
            else:
                logger.info(
                    f"✓ Completed dataset {idx + 1}/{len(dataset_details)}: {dataset_name}"
                )
                results.append(
                    {
                        "dataset": dataset_detail,
                        "success": True,
                        "result": result,
                    }
                )

        write_json(step_2_path, results)
        logger.info("Step 2 results cached")

    logger.info("=" * 60)
    logger.info("Pipeline completed successfully")
    logger.info("=" * 60)

    # Step 3: Gather information for datasets not found in database
    step_3_path = cache_dir / "step_3_results.json"
    step_3_results = None
    datasets_not_found = []

    for step_2_result in results:
        if step_2_result.get("success") and step_2_result.get("result"):
            result_text = str(step_2_result["result"])
            # Check if dataset was actually found by parsing the result
            # parse_dataset_info returns None if dataset not found or if no valid dataset ID found
            dataset_info = parse_dataset_info(result_text)
            if dataset_info is None:
                # Also check for explicit "Dataset not found" string for backward compatibility
                if "Dataset not found" in result_text:
                    datasets_not_found.append(step_2_result["dataset"])
                else:
                    # If parse_dataset_info returns None and no explicit "Dataset not found",
                    # it means the agent didn't find a valid dataset ID, so treat as not found
                    datasets_not_found.append(step_2_result["dataset"])

    if datasets_not_found:
        # Check for cached results if resuming
        if resume:
            step_3_results = read_json_if_exists(step_3_path)
            if step_3_results:
                logger.info(
                    f"Using cached Step 3 results ({len(step_3_results)} datasets)"
                )

        # Only run step_3 if we don't have cached results (or not resuming)
        if not step_3_results:
            step_3_results = []
            logger.info("=" * 60)
            logger.info(
                f"STEP 3: Gathering information for {len(datasets_not_found)} datasets not found in database"
            )
            logger.info("=" * 60)

            # Get paper title for context
            paper_title = None
            try:
                paper_details = await get_paper_details(arxiv_id)
                # Extract title from paper_details if available
                if paper_details:
                    # Try to parse JSON if it's JSON
                    try:
                        paper_data = json.loads(paper_details)
                        paper_title = paper_data.get("title")
                    except json.JSONDecodeError:
                        # If not JSON, try to extract title from text
                        title_match = re.search(
                            r"Title:\s*(.+?)(?:\n|$)", paper_details, re.IGNORECASE
                        )
                        if title_match:
                            paper_title = title_match.group(1).strip()
            except Exception as e:
                logger.warning(f"Could not get paper title: {e}")

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            step_3_tasks = []

            for idx, dataset_detail in enumerate(datasets_not_found):
                dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")
                logger.info(
                    f"Queuing step_3 for dataset {idx + 1}/{len(datasets_not_found)}: {dataset_name}"
                )

                task = step_3_with_retry(
                    dataset_detail=dataset_detail,
                    arxiv_id=arxiv_id,
                    paper_title=paper_title,
                    semaphore=semaphore,
                )
                step_3_tasks.append(task)

                if idx < len(datasets_not_found) - 1:
                    await asyncio.sleep(DELAY_BETWEEN_STARTS)

            logger.info(
                f"Running {len(step_3_tasks)} step_3 tasks with rate limiting..."
            )
            step_3_raw_results = await asyncio.gather(
                *step_3_tasks, return_exceptions=False
            )

            # Process step_3 results
            for idx, (dataset_detail, result) in enumerate(step_3_raw_results):
                dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")

                if isinstance(result, Exception):
                    logger.error(
                        f"Error in step_3 for dataset {dataset_name}: {result}"
                    )
                    step_3_results.append(
                        {
                            "dataset": dataset_detail,
                            "success": False,
                            "error": str(result),
                            "result": None,
                        }
                    )
                else:
                    logger.info(
                        f"✓ Completed step_3 for dataset {idx + 1}/{len(datasets_not_found)}: {dataset_name}"
                    )
                    step_3_results.append(
                        {
                            "dataset": dataset_detail,
                            "success": result is not None,
                            "result": result.model_dump() if result else None,
                        }
                    )

                write_json(step_3_path, step_3_results)
                logger.info("Step 3 results cached")
    else:
        logger.info("STEP 3: Skipped (all datasets found in database)")
        if resume:
            step_3_results = read_json_if_exists(step_3_path)
            if step_3_results:
                logger.info(
                    f"Using cached Step 3 results ({len(step_3_results)} datasets)"
                )

    if step_3_results is None:
        step_3_results = []

    # Step 4: Add datasets gathered in step_3 to database
    step_4_path = cache_dir / "step_4_results.json"
    step_4_results = None
    datasets_to_add = []

    if skip_addition:
        logger.info("STEP 4: Skipped (--skip-addition flag enabled)")
        if resume:
            step_4_results = read_json_if_exists(step_4_path)
            if step_4_results:
                logger.info(
                    f"Using cached Step 4 results ({len(step_4_results)} datasets)"
                )
        if step_4_results is None:
            step_4_results = []
    else:
        if resume:
            step_4_results = read_json_if_exists(step_4_path)
            if step_4_results:
                logger.info(
                    f"Using cached Step 4 results ({len(step_4_results)} datasets)"
                )

        if not step_4_results:
            for step_3_result in step_3_results:
                if step_3_result.get("success") and step_3_result.get("result"):
                    datasets_to_add.append(step_3_result)

            if datasets_to_add:
                logger.info("=" * 60)
                logger.info(
                    f"STEP 4: Adding {len(datasets_to_add)} datasets to database"
                )
                logger.info("=" * 60)

                semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
                step_4_tasks = []

                for idx, step_3_result in enumerate(datasets_to_add):
                    dataset_detail = step_3_result["dataset"]
                    dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")
                    logger.info(
                        f"Queuing step_4 for dataset {idx + 1}/{len(datasets_to_add)}: {dataset_name}"
                    )

                    task = step_4_with_retry(
                        dataset_detail=dataset_detail,
                        step_3_result=step_3_result["result"],
                        arxiv_id=arxiv_id,
                        semaphore=semaphore,
                    )
                    step_4_tasks.append(task)

                    if idx < len(datasets_to_add) - 1:
                        await asyncio.sleep(DELAY_BETWEEN_STARTS)

                logger.info(
                    f"Running {len(step_4_tasks)} step_4 tasks with rate limiting..."
                )
                step_4_raw_results = await asyncio.gather(
                    *step_4_tasks, return_exceptions=False
                )

                # Initialize results list
                step_4_results = []

                # Process step_4 results
                for idx, (dataset_detail, result) in enumerate(step_4_raw_results):
                    dataset_name = dataset_detail.get("dataset_name", f"Dataset_{idx}")

                    if isinstance(result, Exception):
                        logger.error(
                            f"Error in step_4 for dataset {dataset_name}: {result}"
                        )
                        step_4_results.append(
                            {
                                "dataset": dataset_detail,
                                "success": False,
                                "error": str(result),
                                "result": None,
                            }
                        )
                    else:
                        logger.info(
                            f"✓ Completed step_4 for dataset {idx + 1}/{len(datasets_to_add)}: {dataset_name}"
                        )
                        step_4_results.append(
                            {
                                "dataset": dataset_detail,
                                "success": "Successfully created dataset"
                                in str(result),
                                "result": result,
                            }
                        )

                write_json(step_4_path, step_4_results)
                logger.info("Step 4 results cached")
        else:
            logger.info("STEP 4: Skipped (no datasets to add)")
            if step_4_results is None:
                step_4_results = []

    # Step 5: Normalize evaluation results datasets
    step_5_normalized_path = cache_dir / "step_5_normalized.json"
    normalized_result = None
    normalized_evaluation_results = evaluation_results  # Default to original

    if skip_addition:
        logger.info("STEP 5: Skipped (--skip-addition flag enabled)")
        if resume:
            normalized_result = read_json_if_exists(step_5_normalized_path)
            if normalized_result:
                logger.info("Using cached Step 5 normalized results")
                normalized_evaluation_results = normalized_result.get(
                    "normalized", evaluation_results
                )
    else:
        # Check cache first if resuming
        if resume:
            normalized_result = read_json_if_exists(step_5_normalized_path)
            if normalized_result:
                logger.info("Using cached Step 5 normalized results")
                normalized_evaluation_results = normalized_result.get(
                    "normalized", evaluation_results
                )

        # Run normalization if not cached
        if not normalized_result:
            logger.info("=" * 60)
            logger.info("STEP 5: Normalizing evaluation results datasets")
            logger.info("=" * 60)

            from extract_evaluation_results.step_5 import normalize_evaluation_datasets

            normalized_result = normalize_evaluation_datasets(
                arxiv_id=arxiv_id,
                evaluation_results=evaluation_results,
                step_2_results=results,
                step_4_results=step_4_results,
            )

            write_json(step_5_normalized_path, normalized_result)
            logger.info("Step 5 normalization results cached")

            normalized_evaluation_results = normalized_result.get(
                "normalized", evaluation_results
            )
            logger.info(
                f"Step 5 completed: {normalized_result.get('mapped', 0)} mapped, "
                f"{normalized_result.get('unresolved', 0)} unresolved"
            )

    # Step 6: Add to database (optional)
    aligned_results_path = cache_dir / "aligned_results.json"
    step_6_result_path = cache_dir / "step_6_result.txt"
    aligned_results = None
    step_6_result = None
    step_6_error = None

    if skip_addition:
        logger.info("STEP 6: Skipped (--skip-addition flag enabled)")
        if resume:
            aligned_results = read_json_if_exists(aligned_results_path)
            if step_6_result_path.exists():
                try:
                    step_6_result = step_6_result_path.read_text()
                except IOError as e:
                    logger.warning(f"Failed to read cached step 6 result: {e}")
                    step_6_result = None
            if aligned_results or step_6_result:
                logger.info("Using cached Step 6 results")
        if aligned_results is None:
            aligned_results = []
    elif not skip_step_6:
        # Always recompute alignment (it's cheap and depends on current DB state)
        # Use normalized evaluation results instead of original
        aligned_results, alignment_error = align_evaluation_results(
            arxiv_id=arxiv_id,
            evaluation_results=normalized_evaluation_results,
            step_2_results=results,
            step_4_results=step_4_results or [],
        )

        if alignment_error:
            logger.error(f"Alignment failed: {alignment_error}")
            step_6_error = alignment_error
            aligned_results = []
        else:
            write_json(aligned_results_path, aligned_results)

        # Check cache for step_6_result if resume enabled
        if resume and aligned_results:
            cached_step_6_result = None
            if step_6_result_path.exists():
                try:
                    cached_step_6_result = step_6_result_path.read_text()
                except IOError as e:
                    logger.warning(f"Failed to read cached step 6 result: {e}")

            if cached_step_6_result:
                step_6_result = cached_step_6_result
                logger.info("Using cached Step 6 result")
            else:
                # Run step 6 if we have aligned results but no cached result
                aligned_results, step_6_result, step_6_error = await run_step_6(
                    arxiv_id, normalized_evaluation_results, results, step_4_results
                )
                if step_6_result:
                    write_text(step_6_result_path, step_6_result)
                    logger.info("Step 6 result cached")
        elif aligned_results:
            # Run step 6 normally if not resuming
            aligned_results, step_6_result, step_6_error = await run_step_6(
                arxiv_id, normalized_evaluation_results, results, step_4_results
            )
            if step_6_result:
                write_text(step_6_result_path, step_6_result)
                logger.info("Step 6 result cached")
        else:
            logger.warning("No evaluation results to add to database")
            aligned_results = []
    else:
        logger.info("STEP 6: Skipped (--skip-step-6 flag enabled)")
        if resume:
            aligned_results = read_json_if_exists(aligned_results_path)
            if aligned_results:
                logger.info(
                    f"Using cached aligned results ({len(aligned_results)} results)"
                )
        if aligned_results is None:
            aligned_results = []

    return {
        "success": True,
        "step_1_response": step_1_data,
        "step_2_results": results,
        "step_3_results": step_3_results,
        "step_4_results": step_4_results,
        "step_5_normalized": normalized_result,
        "aligned_results": aligned_results,
        "step_6_result": step_6_result,
        "step_6_error": step_6_error,
    }


def print_summary(result: dict):
    """Print pipeline summary."""
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Success: {result.get('success', False)}")

    if "error" in result:
        print(f"Error: {result['error']}")

    # Step 1 results
    if result.get("step_1_response"):
        step_1_data = result["step_1_response"]
        print("\nStep 1 Results:")
        print(
            f"  - Evaluation results: {len(step_1_data.get('evaluation_results', []))}"
        )
        print(f"  - Datasets found: {len(step_1_data.get('dataset_details', []))}")

    # Step 2 results
    if result.get("step_2_results"):
        step_2_results = result["step_2_results"]
        successful = sum(1 for r in step_2_results if r.get("success"))
        failed = len(step_2_results) - successful

        print("\nStep 2 Results:")
        print(f"  - Successfully processed: {successful}")
        print(f"  - Failed: {failed}")

        for idx, step_2_result in enumerate(step_2_results):
            dataset_name = step_2_result["dataset"].get(
                "dataset_name", f"Dataset_{idx}"
            )
            status = "✓" if step_2_result.get("success") else "✗"
            print(f"    {status} {dataset_name}")

            if step_2_result.get("success") and step_2_result.get("result"):
                dataset_info = parse_dataset_info(step_2_result["result"])
                if dataset_info:
                    print("      → Status: Found in database")
                    print(f"         ID: {dataset_info.get('id', 'N/A')}")
                    print(f"         Name: {dataset_info.get('name', 'Unknown')}")
                    if dataset_info.get("slug"):
                        print(f"         Slug: {dataset_info.get('slug')}")
                    if dataset_info.get("hf_url"):
                        print(f"         HF URL: {dataset_info.get('hf_url')}")
                else:
                    print("      → Status: NOT found in database")
            elif not step_2_result.get("success"):
                print(f"      → Error: {step_2_result.get('error', 'Unknown error')}")

    # Step 3 results
    if result.get("step_3_results"):
        step_3_results = result["step_3_results"]
        successful = sum(1 for r in step_3_results if r.get("success"))
        failed = len(step_3_results) - successful

        print("\nStep 3 Results:")
        print(f"  - Successfully processed: {successful}")
        print(f"  - Failed: {failed}")

        for idx, step_3_result in enumerate(step_3_results):
            dataset_name = step_3_result["dataset"].get(
                "dataset_name", f"Dataset_{idx}"
            )
            status = "✓" if step_3_result.get("success") else "✗"
            print(f"    {status} {dataset_name}")

            if step_3_result.get("success") and step_3_result.get("result"):
                dataset_info = step_3_result["result"]
                print("      → Status: Information gathered")
                if dataset_info.get("full_name"):
                    print(f"         Full Name: {dataset_info.get('full_name')}")
                if dataset_info.get("description"):
                    desc = dataset_info.get("description")
                    if len(desc) > 100:
                        desc = desc[:100] + "..."
                    print(f"         Description: {desc}")
                if dataset_info.get("hf_url"):
                    print(f"         HF URL: {dataset_info.get('hf_url')}")
                if dataset_info.get("arxiv_id"):
                    print(f"         ArXiv ID: {dataset_info.get('arxiv_id')}")
                if dataset_info.get("conference_url"):
                    print(
                        f"         Conference URL: {dataset_info.get('conference_url')}"
                    )
            elif not step_3_result.get("success"):
                print(f"      → Error: {step_3_result.get('error', 'Unknown error')}")
    elif result.get("step_2_results"):
        # Check if any datasets were not found
        datasets_not_found = sum(
            1
            for r in result["step_2_results"]
            if r.get("success")
            and r.get("result")
            and "Dataset not found" in str(r.get("result"))
        )
        if datasets_not_found == 0:
            print("\nStep 3 Results:")
            print("  - Skipped (all datasets found in database)")

    # Step 4 results
    if result.get("step_4_results"):
        step_4_results = result["step_4_results"]
        successful = sum(1 for r in step_4_results if r.get("success"))
        failed = len(step_4_results) - successful

        print("\nStep 4 Results:")
        print(f"  - Successfully added: {successful}")
        print(f"  - Failed: {failed}")

        for idx, step_4_result in enumerate(step_4_results):
            dataset_name = step_4_result["dataset"].get(
                "dataset_name", f"Dataset_{idx}"
            )
            status = "✓" if step_4_result.get("success") else "✗"
            print(f"    {status} {dataset_name}")

            if step_4_result.get("success") and step_4_result.get("result"):
                result_text = str(step_4_result["result"])
                dataset_info = parse_dataset_info(result_text)
                if dataset_info:
                    print("      → Status: Added to database")
                    print(f"         ID: {dataset_info.get('id', 'N/A')}")
                    print(f"         Name: {dataset_info.get('name', 'Unknown')}")
                    if dataset_info.get("slug"):
                        print(f"         Slug: {dataset_info.get('slug')}")
                else:
                    print(f"      → Result: {result_text[:200]}...")
            elif not step_4_result.get("success"):
                print(f"      → Error: {step_4_result.get('error', 'Unknown error')}")
    elif result.get("step_3_results"):
        # Check if any datasets were gathered in step_3
        datasets_gathered = sum(
            1 for r in result["step_3_results"] if r.get("success") and r.get("result")
        )
        if datasets_gathered == 0:
            print("\nStep 4 Results:")
            print("  - Skipped (no datasets gathered in step 3)")

    # Step 5 results (normalization)
    if result.get("step_5_normalized"):
        step_5_normalized = result["step_5_normalized"]
        print("\nStep 5 Results (Normalization):")
        print(
            f"  - Total evaluation results: {len(step_5_normalized.get('normalized', []))}"
        )
        print(f"  - Successfully mapped: {step_5_normalized.get('mapped', 0)}")
        print(f"  - Unresolved: {step_5_normalized.get('unresolved', 0)}")

        dataset_mapping = step_5_normalized.get("dataset_mapping", {})
        if dataset_mapping:
            print(f"  - Dataset mappings: {len(dataset_mapping)}")
            for original_name, mapping in list(dataset_mapping.items())[:5]:
                print(
                    f"    • '{original_name}' → '{mapping['canonical_name']}' (ID: {mapping['id']})"
                )
            if len(dataset_mapping) > 5:
                print(f"    ... and {len(dataset_mapping) - 5} more")

    # Step 6 results (database insertion)
    if result.get("aligned_results"):
        print("\nStep 6 Results (Database Insertion):")
        print(
            f"  - Aligned evaluation results: {len(result.get('aligned_results', []))}"
        )
        if result.get("step_6_error"):
            print(f"  - Error: {result['step_6_error']}")
        elif result.get("step_6_result"):
            print("  - Status: ✓ Evaluation results added to database")
            result_preview = result["step_6_result"][:300]
            if len(result["step_6_result"]) > 300:
                result_preview += "..."
            print(f"  - Result: {result_preview}")

    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper and submit them to the database."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        default="2406.09414",
        help="The ArXiv ID of the paper to process",
    )
    parser.add_argument(
        "--skip-step-6",
        action="store_true",
        help="Skip step 6 (do not add evaluation results to database)",
    )
    parser.add_argument(
        "--skip-addition",
        action="store_true",
        help="Skip step 4, 5, and 6 (do not add datasets, normalize, or add evaluation results to database)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from cached results if available (skips re-running completed steps)",
    )
    args = parser.parse_args()

    result = await run_pipeline(
        args.arxiv_id,
        skip_step_6=args.skip_step_6,
        skip_addition=args.skip_addition,
        resume=args.resume,
    )
    print_summary(result)
    return result


if __name__ == "__main__":
    asyncio.run(main())
