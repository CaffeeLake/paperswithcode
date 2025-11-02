"""
Main script that orchestrates the evaluation result extraction pipeline.

This script:
1. Runs step_1 to extract evaluation results from a paper PDF
2. Runs step_2 for each dataset mentioned in the results to find whether it is already in the database or not (in parallel)

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545
```
"""

import argparse
import asyncio
import json
import logging
import re
from typing import Union

from extract_evaluation_results.step_1 import step_1
from extract_evaluation_results.step_2 import step_2, get_paper_details

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration
MAX_CONCURRENT_REQUESTS = 2  # Limit concurrent requests to avoid rate limits
DELAY_BETWEEN_STARTS = 2.0  # Delay in seconds between starting tasks
MAX_RETRIES = 3  # Maximum number of retries for rate limit errors
RETRY_BASE_DELAY = 5.0  # Base delay in seconds for exponential backoff


async def step_2_with_retry(
    arxiv_id: str,
    dataset_detail: dict,
    evaluation_results: list,
    paper_details: str,
    use_web_search: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, Union[str, Exception]]:
    """Run step_2 with rate limiting and retry logic.

    Returns:
        Tuple of (dataset_detail, result_string or exception)
    """
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

                # Check if it's a rate limit error
                is_rate_limit = (
                    "429" in error_str
                    or "rate_limit" in error_str.lower()
                    or "Rate limit" in error_str
                )

                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    # Extract wait time from error message if available
                    wait_time = RETRY_BASE_DELAY * (2**attempt)

                    # Try to extract wait time from error message
                    wait_match = re.search(r"Please try again in ([\d.]+)s", error_str)
                    if wait_match:
                        wait_time = float(wait_match.group(1)) + 1.0  # Add 1s buffer

                    logger.warning(
                        f"Rate limit hit for dataset '{dataset_name}'. "
                        f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Not a rate limit error, or max retries reached
                    logger.error(
                        f"Error processing dataset '{dataset_name}': {error_str}"
                    )
                    return (dataset_detail, e)

        # If we get here, all retries failed
        return (dataset_detail, Exception(f"Failed after {MAX_RETRIES} attempts"))


async def run_pipeline(arxiv_id: str) -> dict:
    """Run the complete evaluation extraction pipeline.

    Args:
        arxiv_id: The ArXiv ID of the paper to process

    Returns:
        Dictionary with step_1 results and step_2 results for each dataset
    """
    logger.info(f"Starting pipeline for paper: {arxiv_id}")

    # Step 1: Extract evaluation results from paper
    logger.info("=" * 60)
    logger.info("STEP 1: Extracting evaluation results from paper")
    logger.info("=" * 60)
    step_1_response = await step_1(arxiv_id)

    if step_1_response is None:
        logger.error("Step 1 failed: Could not extract evaluation results")
        return {
            "success": False,
            "error": "Step 1 failed: Could not extract evaluation results",
            "step_1_response": None,
            "step_2_results": [],
        }

    # Parse step_1 response
    try:
        step_1_data = json.loads(step_1_response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse step_1 response as JSON: {e}")
        logger.error(f"Response: {step_1_response[:500]}...")
        return {
            "success": False,
            "error": f"Failed to parse step_1 response as JSON: {e}",
            "step_1_response": step_1_response,
            "step_2_results": [],
        }

    evaluation_results = step_1_data.get("evaluation_results", [])
    dataset_details = step_1_data.get("dataset_details", [])

    logger.info(f"Step 1 completed: Found {len(evaluation_results)} evaluation results")
    logger.info(f"Found {len(dataset_details)} datasets mentioned in the paper")

    if not dataset_details:
        logger.warning("No datasets found in step_1 output")
        return {
            "success": True,
            "step_1_response": step_1_data,
            "step_2_results": [],
            "message": "No datasets found to process",
        }

    # Step 2: Process each dataset with rate limiting
    logger.info("=" * 60)
    logger.info(f"STEP 2: Processing {len(dataset_details)} datasets")
    logger.info(
        f"Using rate limiting: max {MAX_CONCURRENT_REQUESTS} concurrent requests"
    )
    logger.info("=" * 60)

    # Get paper details once (shared for all datasets)
    paper_details = await get_paper_details(arxiv_id)

    # Check if web search is available
    import os

    use_web_search = bool(os.getenv("EXA_API_KEY"))
    if not use_web_search:
        logger.warning(
            "EXA_API_KEY not found. Web search disabled for dataset finding."
        )

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # Create tasks with staggered starts to avoid burst traffic
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

        # Stagger task starts to avoid burst traffic
        if idx < len(dataset_details) - 1:  # Don't delay after last task
            await asyncio.sleep(DELAY_BETWEEN_STARTS)

    # Run all tasks (they will execute with rate limiting)
    logger.info(f"Running {len(tasks)} dataset processing tasks with rate limiting...")
    step_2_results = await asyncio.gather(*tasks, return_exceptions=False)

    # Process results
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

    return {
        "success": True,
        "step_1_response": step_1_data,
        "step_2_results": results,
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper and process datasets."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        required=False,
        default="2406.09414",
        help="The ArXiv ID of the paper to process",
    )
    args = parser.parse_args()

    result = await run_pipeline(args.arxiv_id)

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Success: {result.get('success', False)}")

    if "error" in result:
        print(f"Error: {result['error']}")

    if result.get("step_1_response"):
        step_1_data = result["step_1_response"]
        print("\nStep 1 Results:")
        print(
            f"  - Evaluation results: {len(step_1_data.get('evaluation_results', []))}"
        )
        print(f"  - Datasets found: {len(step_1_data.get('dataset_details', []))}")

    if result.get("step_2_results"):
        print("\nStep 2 Results:")
        successful = sum(1 for r in result["step_2_results"] if r.get("success"))
        failed = len(result["step_2_results"]) - successful
        print(f"  - Successfully processed: {successful}")
        print(f"  - Failed: {failed}")

        for idx, step_2_result in enumerate(result["step_2_results"]):
            dataset_name = step_2_result["dataset"].get(
                "dataset_name", f"Dataset_{idx}"
            )
            status = "✓" if step_2_result.get("success") else "✗"
            print(f"    {status} {dataset_name}")

            # Print the actual result if available
            if step_2_result.get("success") and step_2_result.get("result"):
                result_text = step_2_result["result"]
                # Check if dataset was found or not
                if "Dataset not found" in result_text:
                    print("      → Dataset NOT found in database")
                else:
                    # Try to parse as JSON to show dataset details
                    try:
                        dataset_info = json.loads(result_text)
                        if isinstance(dataset_info, dict):
                            print(
                                f"      → Found: {dataset_info.get('name', 'Unknown')} (ID: {dataset_info.get('id', 'N/A')}, Slug: {dataset_info.get('slug', 'N/A')})"
                            )
                        else:
                            print(f"      → Result: {result_text[:200]}...")
                    except (json.JSONDecodeError, AttributeError):
                        # If not JSON, show first part of result
                        print(f"      → Result: {result_text[:200]}...")
            elif not step_2_result.get("success") and "error" in step_2_result:
                print(f"      Error: {step_2_result['error']}")

    print("=" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
