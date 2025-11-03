"""
Main script that orchestrates the evaluation result extraction pipeline.

This script:
1. Runs step_1 to extract evaluation results from a paper PDF
2. Runs step_2 for each dataset mentioned in the results to find whether it is already in the database or not (in parallel)
3. Optionally runs step_5 to align evaluation results with database IDs and add them to the database

You can run it like so:

```bash
# Run all steps (including step 5)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545

# Run only steps 1 and 2 (skip step 5)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --skip-step-5
```

Note: Step 5 only processes papers whose evaluation results are from datasets that are already present in the database.
"""

import argparse
import asyncio
import json
import logging
import os
import re
from typing import Optional, Union

from backend.database.connection import db_manager
from backend.services.paper_service import PaperService
from backend.services.dataset_service import DatasetService

from extract_evaluation_results.step_1 import step_1
from extract_evaluation_results.step_2 import step_2, get_paper_details
# step_5 imported conditionally in run_step_5() to avoid import errors when skipping step 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration
MAX_CONCURRENT_REQUESTS = 2
DELAY_BETWEEN_STARTS = 2.0
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5.0


def extract_dataset_id(result_text: str) -> Optional[int]:
    """Extract dataset ID from step_2 result text."""
    if "Dataset not found" in result_text:
        return None

    # Try JSON format first
    try:
        dataset_info = json.loads(result_text)
        if isinstance(dataset_info, dict) and dataset_info.get("found"):
            return dataset_info.get("id")
    except (json.JSONDecodeError, AttributeError):
        pass

    # Try tool result format: "Found dataset: ID=X, Name=Y, Slug=Z"
    id_match = re.search(r"ID=(\d+)", result_text)
    return int(id_match.group(1)) if id_match else None


def parse_dataset_info(result_text: str) -> Optional[dict]:
    """Parse dataset information from step_2 result."""
    if "Dataset not found" in result_text:
        return None

    # Try JSON format
    try:
        dataset_info = json.loads(result_text)
        if isinstance(dataset_info, dict) and dataset_info.get("found"):
            return dataset_info
    except (json.JSONDecodeError, AttributeError):
        pass

    # Try tool result format
    if "Found dataset" in result_text:
        info = {"found": True}
        for field in ["ID", "Name", "Slug", "HF URL"]:
            match = re.search(rf"{field}=([^,]+)", result_text)
            if match:
                key = field.lower().replace(" ", "_")
                info[key] = match.group(1).strip()
        return info if info.get("id") else None

    return None


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
                        f"Error processing dataset '{dataset_name}': {error_str}"
                    )
                    return (dataset_detail, e)

        return (dataset_detail, Exception(f"Failed after {MAX_RETRIES} attempts"))


def align_evaluation_results(
    arxiv_id: str,
    evaluation_results: list,
    step_2_results: list,
) -> tuple[list, str]:
    """Align evaluation results with database IDs (paper_id, task_id, dataset_id)."""
    session = db_manager.session_local()

    # Get paper_id
    paper_service = PaperService(session)
    paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
    paper_id = paper.id

    # Build dataset_name -> dataset_id mapping
    dataset_name_to_id = {}
    dataset_service = DatasetService(session)

    for step_2_result in step_2_results:
        if not step_2_result.get("success"):
            continue

        dataset_id = extract_dataset_id(step_2_result.get("result", ""))
        if dataset_id:
            dataset_name = step_2_result["dataset"].get("dataset_name", "")
            dataset_name_to_id[dataset_name.lower()] = dataset_id
            logger.info(f"Mapped dataset '{dataset_name}' to ID {dataset_id}")

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


async def run_step_5(
    arxiv_id: str, evaluation_results: list, step_2_results: list
) -> tuple[list, Optional[str], Optional[str]]:
    """Run step 5 to add evaluation results to database.

    Returns:
        Tuple of (aligned_results, step_5_result, error_message)
    """
    if not evaluation_results or not any(
        r.get("success") and extract_dataset_id(str(r.get("result", ""))) is not None
        for r in step_2_results
    ):
        logger.info(
            "Skipping Step 5: No evaluation results or no datasets found in database"
        )
        return [], None, None

    logger.info("=" * 60)
    logger.info("STEP 5: Aligning evaluation results and adding to database")
    logger.info("=" * 60)

    aligned_results, alignment_error = align_evaluation_results(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
    )

    if alignment_error:
        logger.error(f"Alignment failed: {alignment_error}")
        return [], None, alignment_error

    if not aligned_results:
        logger.warning("No evaluation results to add to database")
        return [], None, None

    # Import step_5 only when needed (lazy import)
    from extract_evaluation_results.step_5 import step_5

    paper_details = await get_paper_details(arxiv_id)
    step_5_result = await step_5(
        arxiv_id=arxiv_id,
        aligned_evaluation_results=aligned_results,
        paper_details=paper_details,
    )
    logger.info(
        f"Step 5 completed: {step_5_result[:200] if step_5_result else 'No result'}..."
    )
    return aligned_results, step_5_result, None


async def run_pipeline(arxiv_id: str, skip_step_5: bool = False) -> dict:
    """Run the complete evaluation extraction pipeline."""
    logger.info(f"Starting pipeline for paper: {arxiv_id}")

    # Step 1: Extract evaluation results
    logger.info("=" * 60)
    logger.info("STEP 1: Extracting evaluation results from paper")
    logger.info("=" * 60)

    step_1_response = await step_1(arxiv_id)
    if step_1_response is None:
        return {
            "success": False,
            "error": "Step 1 failed: Could not extract evaluation results",
            "step_1_response": None,
            "step_2_results": [],
        }

    step_1_data = json.loads(step_1_response)

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
        logger.info(f"Queuing dataset {idx + 1}/{len(dataset_details)}: {dataset_name}")

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

    logger.info(f"Running {len(tasks)} dataset processing tasks with rate limiting...")
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

    logger.info("=" * 60)
    logger.info("Pipeline completed successfully")
    logger.info("=" * 60)

    # Step 5: Add to database (optional)
    aligned_results = []
    step_5_result = None
    step_5_error = None

    if not skip_step_5:
        aligned_results, step_5_result, step_5_error = await run_step_5(
            arxiv_id, evaluation_results, results
        )

    return {
        "success": True,
        "step_1_response": step_1_data,
        "step_2_results": results,
        "aligned_results": aligned_results,
        "step_5_result": step_5_result,
        "step_5_error": step_5_error,
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

    # Step 5 results
    if result.get("aligned_results"):
        print("\nStep 5 Results:")
        print(
            f"  - Aligned evaluation results: {len(result.get('aligned_results', []))}"
        )
        if result.get("step_5_error"):
            print(f"  - Error: {result['step_5_error']}")
        elif result.get("step_5_result"):
            print("  - Status: ✓ Evaluation results added to database")
            result_preview = result["step_5_result"][:300]
            if len(result["step_5_result"]) > 300:
                result_preview += "..."
            print(f"  - Result: {result_preview}")

    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper and process datasets."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        default="2406.09414",
        help="The ArXiv ID of the paper to process",
    )
    parser.add_argument(
        "--skip-step-5",
        action="store_true",
        help="Skip step 5 (do not add evaluation results to database)",
    )
    args = parser.parse_args()

    result = await run_pipeline(args.arxiv_id, skip_step_5=args.skip_step_5)
    print_summary(result)
    return result


if __name__ == "__main__":
    asyncio.run(main())
