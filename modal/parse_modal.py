"""
Modal deployment script for evaluation result extraction pipeline.

This script runs the evaluation extraction workflow on Modal for scalable processing.

Installation:
    pip install modal

Setup:
    1. Create Modal account: modal.com
    2. Install: pip install modal
    3. Authenticate: modal token new
    4. Create secrets in Modal dashboard with your environment variables

Usage:
    # Test single paper
    modal run modal/parse_modal.py --arxiv-id 2201.03545

    # Process batch of papers (from file)
    modal run modal/parse_modal.py --batch modal/arxiv_ids_sample.txt

    # Process batch with custom parallelism
    modal run modal/parse_modal.py --batch modal/arxiv_ids_sample.txt --max-workers 50

    # Deploy as persistent app
    modal deploy modal/parse_modal.py

    # Then invoke remotely
    modal run modal/parse_modal.py::process_papers --arxiv-ids '["2201.03545", "2406.09414"]'
"""

import modal
import sys

# ============================================================================
# Modal App Configuration
# ============================================================================

app = modal.App("paperswithcode-extraction")

# Define the container image with all dependencies
image = (
    modal.Image.debian_slim()
    .apt_install("postgresql-client", "git")
    .pip_install(
        "sqlalchemy",
        "psycopg2-binary",
        "pydantic",
        "requests",
        "anthropic",
        "beautifulsoup4",
        "aiohttp",
        "python-dotenv",
        "pypdf",
    )
    .copy_local_dir(
        "/root/python_projects/paperswithcode/backend",
        "/app/backend",
    )
    .copy_local_dir(
        "/root/python_projects/paperswithcode/extract_evaluation_results",
        "/app/extract_evaluation_results",
    )
    .env({"PYTHONPATH": "/app"})
)

# ============================================================================
# Modal Function Definitions
# ============================================================================


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("paperswithcode-db")
    ],  # Create this in Modal dashboard
    timeout=900,  # 15 minutes per paper
    retries=modal.Retries(
        max_retries=2,
        backoff_coefficient=2.0,
        initial_delay=60.0,
    ),
    cpu=2.0,
    memory=4096,  # 4GB RAM
)
async def process_single_paper(
    arxiv_id: str,
    skip_step_6: bool = False,
    skip_addition: bool = False,
    resume: bool = True,
) -> dict:
    """
    Process a single paper through the evaluation extraction pipeline.

    Args:
        arxiv_id: The ArXiv ID of the paper
        skip_step_6: Skip step 6 (don't add evaluations to DB)
        skip_addition: Skip steps 4-7 (don't add datasets or evaluations)
        resume: Resume from cached results if available

    Returns:
        Dictionary with processing results
    """
    import sys

    sys.path.insert(0, "/app")

    from extract_evaluation_results.parse import run_pipeline
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Starting processing for paper: {arxiv_id}")
        result = await run_pipeline(
            arxiv_id=arxiv_id,
            skip_step_6=skip_step_6,
            skip_addition=skip_addition,
            resume=resume,
        )

        logger.info(f"Completed processing for paper: {arxiv_id}")
        return {
            "arxiv_id": arxiv_id,
            "success": result.get("success", False),
            "error": result.get("error"),
            "message": result.get("message"),
            "summary": {
                "evaluation_results": len(
                    result.get("step_1_response", {}).get("evaluation_results", [])
                ),
                "datasets_found": len(
                    [r for r in result.get("step_2_results", []) if r.get("found")]
                ),
                "datasets_added": len(
                    [r for r in result.get("step_4_results", []) if r.get("success")]
                ),
                "evaluations_added": result.get("step_7_result", {}).get(
                    "added_count", 0
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error processing paper {arxiv_id}: {str(e)}")
        return {
            "arxiv_id": arxiv_id,
            "success": False,
            "error": str(e),
            "message": f"Failed to process paper {arxiv_id}",
        }


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("paperswithcode-db")],
    timeout=3600,  # 1 hour for batch processing
)
async def process_papers_batch(
    arxiv_ids: list[str],
    skip_step_6: bool = False,
    skip_addition: bool = False,
    resume: bool = True,
    max_workers: int = 20,
) -> dict:
    """
    Process multiple papers in parallel with controlled concurrency.

    Args:
        arxiv_ids: List of ArXiv IDs to process
        skip_step_6: Skip step 6 for all papers
        skip_addition: Skip steps 4-7 for all papers
        resume: Resume from cached results
        max_workers: Maximum number of concurrent workers

    Returns:
        Dictionary with batch processing results
    """
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info(f"Starting batch processing for {len(arxiv_ids)} papers")
    logger.info(f"Max concurrent workers: {max_workers}")

    # Process papers in parallel using Modal's map
    results = []
    async for result in process_single_paper.map(
        arxiv_ids,
        kwargs={
            "skip_step_6": skip_step_6,
            "skip_addition": skip_addition,
            "resume": resume,
        },
        order_outputs=False,  # Process as they complete
        return_exceptions=True,  # Don't fail entire batch on single error
    ):
        results.append(result)

        # Log progress
        if isinstance(result, dict):
            arxiv_id = result.get("arxiv_id", "unknown")
            success = result.get("success", False)
            status = "✓" if success else "✗"
            logger.info(
                f"{status} {arxiv_id} - Progress: {len(results)}/{len(arxiv_ids)}"
            )
        else:
            logger.error(f"Exception occurred: {result}")

    # Calculate summary statistics
    successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failed = len(results) - successful

    total_evaluations = sum(
        r.get("summary", {}).get("evaluations_added", 0)
        for r in results
        if isinstance(r, dict)
    )

    summary = {
        "total": len(arxiv_ids),
        "successful": successful,
        "failed": failed,
        "total_evaluations_added": total_evaluations,
    }

    logger.info(f"Batch processing complete: {summary}")

    return {
        "success": True,
        "summary": summary,
        "results": results,
    }


# ============================================================================
# Local Entrypoints (for running from command line)
# ============================================================================


@app.local_entrypoint()
def main(
    arxiv_id: str = None,
    batch: str = None,
    skip_step_6: bool = False,
    skip_addition: bool = False,
    max_workers: int = 20,
):
    """
    Main entrypoint for Modal execution.

    Examples:
        # Single paper
        modal run parse_modal.py --arxiv-id 2201.03545

        # Batch from file
        modal run parse_modal.py --batch arxiv_ids.txt --max-workers 50

        # Skip database insertion (testing)
        modal run parse_modal.py --batch test_ids.txt --skip-addition
    """

    if arxiv_id:
        # Process single paper
        print(f"Processing single paper: {arxiv_id}")
        result = process_single_paper.remote(
            arxiv_id=arxiv_id,
            skip_step_6=skip_step_6,
            skip_addition=skip_addition,
        )
        print_result(result)

    elif batch:
        # Process batch from file
        arxiv_ids = load_arxiv_ids_from_file(batch)
        print(f"Processing {len(arxiv_ids)} papers from {batch}")
        print(f"Max workers: {max_workers}")

        result = process_papers_batch.remote(
            arxiv_ids=arxiv_ids,
            skip_step_6=skip_step_6,
            skip_addition=skip_addition,
            max_workers=max_workers,
        )
        print_batch_result(result)

    else:
        print("Error: Must provide either --arxiv-id or --batch")
        sys.exit(1)


# ============================================================================
# Helper Functions
# ============================================================================


def load_arxiv_ids_from_file(filepath: str) -> list[str]:
    """Load ArXiv IDs from a text file (one per line)."""
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]


def print_result(result: dict):
    """Pretty print a single paper result."""
    print("\n" + "=" * 60)
    print("PROCESSING RESULT")
    print("=" * 60)
    print(f"ArXiv ID: {result.get('arxiv_id')}")
    print(f"Success: {result.get('success')}")

    if result.get("error"):
        print(f"Error: {result.get('error')}")

    summary = result.get("summary", {})
    if summary:
        print(f"\nEvaluation Results: {summary.get('evaluation_results', 0)}")
        print(f"Datasets Found: {summary.get('datasets_found', 0)}")
        print(f"Datasets Added: {summary.get('datasets_added', 0)}")
        print(f"Evaluations Added: {summary.get('evaluations_added', 0)}")

    print("=" * 60)


def print_batch_result(result: dict):
    """Pretty print batch processing results."""
    print("\n" + "=" * 60)
    print("BATCH PROCESSING RESULT")
    print("=" * 60)

    summary = result.get("summary", {})
    print(f"Total Papers: {summary.get('total', 0)}")
    print(f"Successful: {summary.get('successful', 0)}")
    print(f"Failed: {summary.get('failed', 0)}")
    print(f"Total Evaluations Added: {summary.get('total_evaluations_added', 0)}")

    # Show failed papers
    results = result.get("results", [])
    failed_papers = [r for r in results if isinstance(r, dict) and not r.get("success")]

    if failed_papers:
        print(f"\nFailed Papers ({len(failed_papers)}):")
        for r in failed_papers[:10]:  # Show first 10
            arxiv_id = r.get("arxiv_id", "unknown")
            error = r.get("error", "Unknown error")
            print(f"  ✗ {arxiv_id}: {error}")

        if len(failed_papers) > 10:
            print(f"  ... and {len(failed_papers) - 10} more")

    print("=" * 60)


# ============================================================================
# Alternative Entrypoints for Programmatic Use
# ============================================================================


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("paperswithcode-db")],
)
async def process_papers(arxiv_ids: list[str]) -> dict:
    """
    Simple entrypoint for programmatic batch processing.

    Usage:
        modal run parse_modal.py::process_papers --arxiv-ids '["2201.03545", "2406.09414"]'
    """
    return await process_papers_batch(arxiv_ids=arxiv_ids)


if __name__ == "__main__":
    # This allows running locally for testing
    print("This script is designed to run on Modal.")
    print("Usage: modal run modal/parse_modal.py --arxiv-id 2201.03545")
