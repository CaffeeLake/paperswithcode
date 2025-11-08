"""
Main script that orchestrates the evaluation result extraction pipeline (agentic workflow).

This script runs a generic pipeline with configurable steps:
1. Step 1: Extract evaluation results from a paper PDF
2. Step 2: Find datasets in the database (parallel)
3. Step 3: Gather additional information from the web and Hugging Face for datasets not found
4. Step 4: Add new datasets to the database
5. Step 5: Normalize evaluation results datasets using outputs from step 2 and step 4
6. Step 6: Align evaluation results with database IDs and add them to the database

You can run it like so:

```bash
# Run all steps (including step 4, 5, and 6)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545

# Run only steps 1, 2, 3, 4, and 5 (skip step 6 - no database insertion)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --skip-step-6

# Run only steps 1, 2, and 3 (skip step 4, 5, and 6 - no database additions)
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --skip-addition

# Resume from cached results if available
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id 2201.03545 --resume
```

Note: Step 5 normalizes evaluation results datasets. Step 6 only processes papers whose evaluation results are from datasets
that are already present in the database (or were just added in step 4).
"""

import argparse
import asyncio
import logging

from extract_evaluation_results.workflow import Workflow, WorkflowOptions, WorkflowState
from extract_evaluation_results.step_1 import Step1WorkflowStep
from extract_evaluation_results.step_2 import Step2WorkflowStep
from extract_evaluation_results.step_3 import Step3WorkflowStep
from extract_evaluation_results.step_4 import Step4WorkflowStep
from extract_evaluation_results.step_5 import Step5WorkflowStep
from extract_evaluation_results.step_6 import Step6WorkflowStep

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def print_summary(state) -> None:
    """Print workflow summary from state."""
    print("\n" + "=" * 60)
    print("WORKFLOW SUMMARY")
    print("=" * 60)
    print(f"Success: {state.success}")

    if state.error:
        print(f"Error: {state.error}")
        return

    # Step 1
    evaluation_results = state.data.get("evaluation_results", [])
    dataset_details = state.data.get("dataset_details", [])
    if evaluation_results or dataset_details:
        print(
            f"\nStep 1: {len(evaluation_results)} eval results, "
            f"{len(dataset_details)} datasets"
        )

    # Step 2
    step_2_results = state.data.get("step_2_results", [])
    if step_2_results:
        successful = sum(1 for r in step_2_results if r.get("found"))
        print(f"\nStep 2: {successful}/{len(step_2_results)} datasets found in DB")
        for idx, r in enumerate(step_2_results):
            name = r.get("dataset_input", {}).get("dataset_name", f"Dataset_{idx}")
            status = "✓" if r.get("found") else "✗"
            print(f"  {status} {name}")
            if r.get("found") and r.get("dataset"):
                info = r.get("dataset")
                if info:
                    print(f"     ID: {info.get('id')}, Name: {info.get('name')}")

    # Step 3
    step_3_results = state.data.get("step_3_results", [])
    if step_3_results:
        successful = sum(1 for r in step_3_results if r.get("success"))
        print(f"\nStep 3: {successful}/{len(step_3_results)} datasets info gathered")
        for idx, r in enumerate(step_3_results):
            name = r.get("dataset_input", {}).get("dataset_name", f"Dataset_{idx}")
            status = "✓" if r.get("success") else "✗"
            print(f"  {status} {name}")

    # Step 4
    step_4_results = state.data.get("step_4_results", [])
    if step_4_results:
        successful = sum(1 for r in step_4_results if r.get("success"))
        print(f"\nStep 4: {successful}/{len(step_4_results)} datasets added to DB")
        for idx, r in enumerate(step_4_results):
            name = r.get("dataset_input", {}).get("dataset_name", f"Dataset_{idx}")
            status = "✓" if r.get("success") else "✗"
            print(f"  {status} {name}")

    # Step 5
    normalized = state.data.get("normalized", [])
    mapped = state.data.get("mapped", 0)
    unresolved = state.data.get("unresolved", 0)
    if normalized or mapped or unresolved:
        print(f"\nStep 5: {mapped} mapped, {unresolved} unresolved")
        mapping = state.data.get("dataset_mapping", {})
        if mapping:
            print(f"  Dataset mappings: {len(mapping)}")
            for orig, m in list(mapping.items())[:3]:
                print(f"    '{orig}' → '{m['canonical_name']}' (ID: {m['id']})")
            if len(mapping) > 3:
                print(f"    ... and {len(mapping) - 3} more")

    # Step 6
    step_6_result = state.data.get("step_6_result")
    step_6_error = state.data.get("step_6_error")
    if normalized:
        print(f"\nStep 6: {len(normalized)} evaluation results aligned")
        if step_6_error:
            print(f"  Error: {step_6_error}")
        elif step_6_result:
            print("  ✓ Added to database")

    print("=" * 60)


async def run_pipeline(
    arxiv_id: str,
    skip_step_6: bool = False,
    skip_addition: bool = False,
    resume: bool = False,
) -> dict:
    """
    Run the complete evaluation extraction workflow.

    Args:
        arxiv_id: The ArXiv ID of the paper to process
        skip_step_6: Skip step 6 (do not add evaluation results to database)
        skip_addition: Skip step 4, 5, and 6 (do not add datasets or evaluation results)
        resume: Resume from cached results if available

    Returns:
        Dictionary with workflow results (for backward compatibility)
    """
    # Create workflow options
    options = WorkflowOptions(
        arxiv_id=arxiv_id,
        resume=resume,
        skip_addition=skip_addition,
        skip_step_6=skip_step_6,
    )

    # Build the workflow with all steps
    steps = [
        Step1WorkflowStep(),
        Step2WorkflowStep(),
        Step3WorkflowStep(),
        Step4WorkflowStep(),
        Step5WorkflowStep(),
        Step6WorkflowStep(),
    ]

    workflow = Workflow(steps)

    # Run the workflow
    state = await workflow.run(options)

    # Return result dictionary using state.data
    return {
        "success": state.success,
        "step_1_response": {
            "reasoning": state.data.get("reasoning", ""),
            "evaluation_results": state.data.get("evaluation_results", []),
            "dataset_details": state.data.get("dataset_details", []),
        },
        "step_2_results": state.data.get("step_2_results", []),
        "step_3_results": state.data.get("step_3_results", []),
        "step_4_results": state.data.get("step_4_results", []),
        "step_5_normalized": state.data.get("step_5_normalized"),
        "aligned_results": state.data.get("normalized", []),
        "step_6_result": state.data.get("step_6_result"),
        "step_6_error": state.data.get("step_6_error"),
        "error": state.error,
        "message": state.message,
    }


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

    # Import state from workflow for summary printing
    # Since we're using the backward-compatible dict format, we need to reconstruct
    # a minimal state-like object for the summary
    from extract_evaluation_results.workflow import WorkflowOptions

    options = WorkflowOptions(
        arxiv_id=args.arxiv_id,
        resume=args.resume,
        skip_addition=args.skip_addition,
        skip_step_6=args.skip_step_6,
    )

    state = WorkflowState(
        arxiv_id=args.arxiv_id,
        options=options,
        success=result.get("success", False),
        error=result.get("error"),
        message=result.get("message"),
    )

    # Populate state.data from result
    step_1_response = result.get("step_1_response") or {}
    state.data["evaluation_results"] = step_1_response.get("evaluation_results", [])
    state.data["dataset_details"] = step_1_response.get("dataset_details", [])
    state.data["reasoning"] = step_1_response.get("reasoning", "")
    state.data["step_2_results"] = result.get("step_2_results") or []
    state.data["step_3_results"] = result.get("step_3_results") or []
    state.data["step_4_results"] = result.get("step_4_results") or []
    state.data["normalized"] = result.get("aligned_results") or []
    step_5_normalized = result.get("step_5_normalized") or {}
    state.data["mapped"] = step_5_normalized.get("mapped", 0)
    state.data["unresolved"] = step_5_normalized.get("unresolved", 0)
    state.data["dataset_mapping"] = step_5_normalized.get("dataset_mapping", {})
    state.data["step_6_result"] = result.get("step_6_result")
    state.data["step_6_error"] = result.get("step_6_error")

    print_summary(state)
    return result


if __name__ == "__main__":
    asyncio.run(main())
