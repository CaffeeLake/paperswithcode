"""
This script defines an agent that can add datasets to the SQL database.

**Key Feature**: This step processes all datasets in parallel internally, running multiple agent
instances concurrently for improved performance.

You can run it like so:

```bash
# Process datasets from step_3 output (reads from standardized location)
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --arxiv_id "2406.09414"

# Or add a single dataset directly
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --dataset_details "{\"name\": \"COCO\", \"description\": \"COCO is a large-scale object detection, segmentation, and captioning dataset.\"}"
```
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from extract_evaluation_results.step_base import AgentStep, StepResult
from extract_evaluation_results.utils import get_paper_details, get_formatted_tasks_list
from extract_evaluation_results.tools import (
    add_dataset,
    check_existing_dataset,
    get_tasks_by_area,
)

logger = logging.getLogger(__name__)


def _sanitize_dataset_name(name: str) -> str:
    """Sanitize dataset name by removing problematic characters."""
    return (
        name.replace("→", " to ")
        .replace("(", " ")
        .replace(")", "")
        .replace("[", " ")
        .replace("]", "")
        .lower()
        .strip()
    )


class DatasetDetails(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    hf_url: Optional[str] = None
    paper_url: Optional[str] = None


class Response(BaseModel):
    dataset_successfully_added: bool
    dataset_details: Optional[DatasetDetails] = None


# Input and Output models for the new API
class Step4SingleInput(BaseModel):
    """Input for a single dataset in Step 4."""

    dataset_details_json: str = Field(
        description="JSON string containing dataset details to add to the database"
    )


class Step4Input(BaseModel):
    """Input for Step 4: Dataset Adder - handles multiple datasets."""

    dataset_inputs: list[Step4SingleInput]


class Step4SingleResult(BaseModel):
    """Result for a single dataset addition."""

    dataset_input: dict
    success: bool
    dataset_details: Optional[DatasetDetails] = None
    error_message: Optional[str] = None


def _create_error_result(
    error_message: str, dataset_input: dict = None
) -> Step4SingleResult:
    """Create a standardized error result."""
    return Step4SingleResult(
        dataset_input=dataset_input or {},
        success=False,
        dataset_details=None,
        error_message=error_message,
    )


class Step4Output(BaseModel):
    """Output from Step 4: Dataset Adder - handles multiple datasets."""

    results: list[Step4SingleResult]


dataset_adder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI). This way, people can track progress of state-of-the-art models over time.

## Task

You are an expert in managing datasets in the SQL database of Hugging Face's leaderboards project. Your responsibility includes
adding new datasets to the database with comprehensive information when requested.

A colleague of yours has extracted evaluation results from an ArXiv paper and identified a particular dataset mentioned in the evaluation results which is not yet added to the SQL database.
Another colleague of yours has gathered comprehensive information about the dataset (including description, full name, URLs) and will provide you with the required information.
Your task is to add this dataset to the database.

## CRITICAL: Prevent Duplicate Datasets

**BEFORE adding any dataset, you MUST use the `check_existing_dataset` tool to verify it doesn't already exist.**

Steps to follow:
1. **Check for existence**: Call `check_existing_dataset(dataset_name="<name>")` with the dataset name
2. **If found** (response has `"found": true`):
   - DO NOT add the dataset again
   - Set `dataset_successfully_added = False` (since we're not adding, it already exists)
   - Extract the dataset details from the check_existing_dataset response
   - Return those details in `dataset_details` field with the existing dataset's information
3. **If not found** (response has `"found": false`):
   - Proceed with adding the dataset using the `add_dataset` tool
   - Set `dataset_successfully_added = True`
   - Return the newly created dataset details

**Example workflow:**
```
User: Add dataset "RefCOCO"

Step 1: check_existing_dataset("RefCOCO")
Response: {"found": true, "dataset": {"id": 12, "name": "RefCOCO", ...}}

Step 2: Since found=true, return:
{
  "dataset_successfully_added": false,
  "dataset_details": {
    "id": 12,
    "name": "RefCOCO",
    "slug": "refcoco",
    "description": "...",
    "hf_url": "...",
    "paper_url": "..."
  }
}
```

## Important notes

Datasets are no longer directly linked to tasks. Task-dataset relationships are established via (task, dataset, metric) tuples when evaluations are added to the database.

Ensure you provide all relevant information including:
- name (required): The name of the dataset
- description (required): A description of what the dataset contains and its purpose
- full_name (optional): The full name of the dataset
- url (optional): Main URL for the dataset
- hf_url (optional): Hugging Face dataset URL
- paper_url (optional): URL to the paper that introduced this dataset

{tasks_list}

## Output format

When a dataset is processed (either found existing or added new), return the details in the following Pydantic model:
```python
class DatasetDetails(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    hf_url: Optional[str] = None
    paper_url: Optional[str] = None


class Response(BaseModel):
    dataset_successfully_added: bool  # True if newly added, False if already existed
    dataset_details: Optional[DatasetDetails] = None  # Dataset details (existing or newly added)
```

Return the response as a JSON string. Do not include any other text in your response.
"""


class Step4(AgentStep[Step4Input, Step4Output]):
    """Agent-based step for adding datasets to the database."""

    input_model = Step4Input
    output_model = Step4Output

    def __init__(self):
        super().__init__(
            name="Step4: Dataset Adder",
            description="Adds datasets to the database with comprehensive information",
            instructions=dataset_adder_prompt,
            tools=[
                check_existing_dataset,  # ✨ Check for duplicates before adding
                add_dataset,
                get_tasks_by_area,
            ],
            agent_output_type=Response,
            model="gpt-5-mini",
        )

    async def _process_single_dataset(
        self, dataset_input: Step4SingleInput, formatted_instructions: str
    ) -> Step4SingleResult:
        """
        Process a single dataset through the agent.

        Args:
            dataset_input: Single dataset input data
            formatted_instructions: Pre-formatted instructions with tasks list

        Returns:
            Step4SingleResult with addition outcome
        """
        # Parse dataset details
        try:
            dataset_details = json.loads(dataset_input.dataset_details_json)
        except json.JSONDecodeError as e:
            return _create_error_result(
                f"Invalid JSON in dataset_details: {e}",
                dataset_input={"error": "Invalid JSON"},
            )

        dataset_name = dataset_details.get("name", "Unknown")

        try:
            # Extract paper ArXiv ID if available
            paper_arxiv_id = dataset_details.get("paper_arxiv_id")

            # Build prompt
            prompt_parts = [
                "Add the following dataset to the database. The dataset details are as follows:",
                json.dumps(dataset_details, indent=2),
            ]

            # Fetch and include paper details if arxiv_id is available
            if paper_arxiv_id:
                try:
                    paper_details = await get_paper_details(paper_arxiv_id)
                    prompt_parts.append("\n## Paper details")
                    prompt_parts.append(paper_details)
                except Exception as e:
                    logger.warning(
                        f"Could not fetch paper details for {paper_arxiv_id}: {e}"
                    )

            prompt = "\n".join(prompt_parts)

            # Run the agent for this dataset
            print(f"Adding dataset to database: {dataset_name}")
            agent_response = await self._run_agent(prompt, formatted_instructions)

            # Process the agent output
            if isinstance(agent_response, Response):
                if agent_response.dataset_successfully_added:
                    print(f"✓ Added dataset: {dataset_name}")
                    return Step4SingleResult(
                        dataset_input=dataset_details,
                        success=True,
                        dataset_details=agent_response.dataset_details,
                        error_message=None,
                    )
                else:
                    print(f"✗ Failed to add dataset: {dataset_name}")
                    return Step4SingleResult(
                        dataset_input=dataset_details,
                        success=False,
                        dataset_details=None,
                        error_message="Agent reported dataset addition failure",
                    )
            else:
                raise ValueError(
                    f"Unexpected agent output type: {type(agent_response)}"
                )

        except asyncio.CancelledError as e:
            logger.warning(
                "Agent run cancelled while adding dataset '%s': %s", dataset_name, e
            )
            return _create_error_result(
                "Agent run was cancelled before completion",
                dataset_input=dataset_details,
            )
        except Exception as e:
            print(f"Error adding dataset '{dataset_name}': {str(e)}")
            return _create_error_result(
                f"Error during addition: {str(e)}",
                dataset_input=dataset_details,
            )

    async def run(self, inputs):
        """
        Override run to handle parallel processing of multiple datasets.
        """
        # Validate inputs if dict provided
        if isinstance(inputs, dict):
            try:
                inputs = Step4Input(**inputs)
            except Exception as e:
                return StepResult(
                    success=False,
                    error_message=f"Input validation failed: {e}",
                    outputs=None,
                )

        try:
            # Format instructions once (same for all datasets)
            tasks_list = get_formatted_tasks_list()
            # Use string replacement instead of .format() to avoid issues with curly braces in tasks_list
            formatted_instructions = dataset_adder_prompt.replace(
                "{tasks_list}", tasks_list
            )

            # Process all datasets in parallel - create actual Task objects
            task_objects = [
                asyncio.create_task(
                    self._process_single_dataset(
                        dataset_input=dataset_input,
                        formatted_instructions=formatted_instructions,
                    )
                )
                for dataset_input in inputs.dataset_inputs
            ]

            # Use gather with return_exceptions to collect per-dataset results
            # Shield the gather so external cancellations don't abort in-progress tasks prematurely
            try:
                results = await asyncio.shield(
                    asyncio.gather(*task_objects, return_exceptions=True)
                )
            except asyncio.CancelledError:
                # If gather is cancelled, wait for tasks to complete with a timeout
                logger.warning("Gather was cancelled, waiting for tasks to complete...")
                try:
                    # Use shield to protect the gather from further cancellation
                    results = await asyncio.shield(
                        asyncio.wait_for(
                            asyncio.gather(*task_objects, return_exceptions=True),
                            timeout=300.0,
                        )
                    )
                except asyncio.TimeoutError:
                    logger.error("Tasks timed out after 300 seconds")
                    # Cancel all tasks and create error results
                    for task in task_objects:
                        if not task.done():
                            task.cancel()
                    # Wait for cancellation to complete (ignore CancelledError)
                    try:
                        await asyncio.gather(*task_objects, return_exceptions=True)
                    except Exception:
                        pass  # Ignore any errors during cleanup
                    results = [
                        _create_error_result("Task timed out") for _ in task_objects
                    ]
                except asyncio.CancelledError:
                    # Even the shielded wait was cancelled - tasks may still be running
                    logger.warning(
                        "Shielded wait was also cancelled, checking task status..."
                    )
                    # Check which tasks completed and which didn't
                    results = []
                    for task in task_objects:
                        if task.done():
                            try:
                                results.append(task.result())
                            except Exception as e:
                                results.append(e)
                        else:
                            # Task is still running but we're being cancelled
                            # Cancel it and add error result
                            task.cancel()
                            results.append(_create_error_result("Task was cancelled"))
                    # Wait briefly for cancellations to propagate
                    try:
                        await asyncio.gather(*task_objects, return_exceptions=True)
                    except Exception:
                        pass

            # Check if any tasks were cancelled or raised exceptions
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, asyncio.CancelledError):
                    logger.warning(f"Task {i} was cancelled")
                    successful_results.append(
                        _create_error_result("Task was cancelled")
                    )
                elif isinstance(result, Exception):
                    logger.error(f"Task {i} raised exception: {result}")
                    successful_results.append(_create_error_result(str(result)))
                else:
                    successful_results.append(result)

            # Return successful result with all findings
            return StepResult(
                success=True,
                outputs=Step4Output(results=successful_results),
                error_message=None,
            )

        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and hasattr(current_task, "uncancel"):
                removed = current_task.uncancel()
                if removed:
                    logger.debug(
                        "Step 4 run: removed %d pending cancellation(s)", removed
                    )
            # Handle cancellation gracefully
            logger.warning("Step 4 was cancelled, checking if tasks completed...")
            # Check if all tasks actually completed despite the cancellation
            all_done = all(task.done() for task in task_objects)
            if all_done:
                logger.info("✓ All tasks completed successfully despite cancellation")
                # Collect results from completed tasks
                successful_results = []
                for i, task in enumerate(task_objects):
                    try:
                        result = task.result()
                        successful_results.append(result)
                    except Exception as e:
                        logger.error(f"Task {i} raised exception: {e}")
                        successful_results.append(_create_error_result(str(e)))

                # Return successful result with all findings
                return StepResult(
                    success=True,
                    outputs=Step4Output(results=successful_results),
                    error_message=None,
                )
            else:
                logger.warning("Some tasks did not complete")
                return StepResult(
                    success=False,
                    outputs=None,
                    error_message="Step 4 was cancelled before completion",
                )
        except Exception as e:
            return StepResult(
                success=False, outputs=None, error_message=f"Step 4 failed: {str(e)}"
            )

    async def build_agent_prompt(self, inputs: Step4Input) -> str:
        """
        Not used in the new parallel implementation.
        Kept for compatibility with base class signature.
        """
        raise NotImplementedError("Use _process_single_dataset instead")

    async def process_agent_output(
        self, agent_output: Any, inputs: Step4Input
    ) -> Step4Output:
        """
        Not used in the new parallel implementation.
        Kept for compatibility with base class signature.
        """
        raise NotImplementedError("Use _process_single_dataset instead")

    async def format_instructions(self, inputs: Step4Input) -> str:
        """
        Format instructions with task context.
        """
        # Format instructions with tasks list
        tasks_list = get_formatted_tasks_list()
        # Use string replacement instead of .format() to avoid issues with curly braces in tasks_list
        return dataset_adder_prompt.replace("{tasks_list}", tasks_list)


def get_output_dir(arxiv_id: str):
    """Get the output directory for a given arxiv_id.

    Returns: backend/outputs/evaluation_results/{arxiv_id}
    """
    from pathlib import Path

    output_dir = Path(__file__).parent.parent / "backend" / "outputs"
    eval_results_dir = output_dir / "evaluation_results" / arxiv_id
    eval_results_dir.mkdir(parents=True, exist_ok=True)
    return eval_results_dir


def read_step_3_output(arxiv_id: str) -> list[dict]:
    """Read the step_3 output JSON file and extract successfully gathered dataset information.

    Reads from: backend/outputs/evaluation_results/{arxiv_id}/step_3.json

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        List of dataset detail dicts to add to the database
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_3.json"

    if not json_file.exists():
        raise FileNotFoundError(
            f"Could not find step_3 output file: {json_file}. "
            f"Run step_3.py first to generate the output."
        )

    with open(json_file, "r") as f:
        step_3_data = json.load(f)

    # Extract step_3_results list from the dictionary
    # step_3.json has structure: {"step_3_results": [...]}
    step_3_results = step_3_data.get("step_3_results", [])
    if not step_3_results and isinstance(step_3_data, list):
        # Fallback: if it's already a list (backward compatibility)
        step_3_results = step_3_data

    # Extract datasets that were successfully gathered
    datasets_to_add = []
    for item in step_3_results:
        if item.get("success", False) and item.get("information"):
            info = item["information"]
            dataset_input = item.get("dataset_input", {})

            # Build dataset details for adding to database
            dataset_details = {
                "name": dataset_input.get(
                    "dataset_name", info.get("full_name", "Unknown")
                ),
                "description": info.get("description", ""),
                "full_name": info.get("full_name"),
                "hf_url": info.get("hf_url"),
                "paper_url": info.get("conference_url"),
                "paper_arxiv_id": info.get("arxiv_id") or dataset_input.get("arxiv_id"),
            }
            datasets_to_add.append(dataset_details)

    return datasets_to_add


def write_step_4_output(arxiv_id: str, results: list[dict]) -> None:
    """Write the step_4 output JSON file to the standardized location.

    Writes to: backend/outputs/evaluation_results/{arxiv_id}/step_4.json

    Args:
        arxiv_id: The ArXiv ID of the paper
        results: List of result dicts from step_4
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_4.json"

    json_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"✓ Step 4 output written to: {json_file}")


async def step_4(dataset_details_list: list[dict]) -> list[dict]:
    """Add multiple datasets to the database using the dataset adder agent (wrapper for Step4).

    Args:
        dataset_details_list: List of dataset detail dictionaries, each containing:
            - name: Dataset name (required)
            - description: Dataset description (required)
            - full_name: Optional full name
            - url: Optional main URL
            - hf_url: Optional Hugging Face URL
            - paper_url: Optional paper URL
            - paper_arxiv_id: Optional ArXiv ID of introducing paper (used to fetch paper details)

    Returns:
        List of dictionaries, each with 'dataset_input', 'success', 'dataset_details', and 'error_message' keys
    """
    # Convert dicts to Step4SingleInput models
    single_inputs = [
        Step4SingleInput(dataset_details_json=json.dumps(details))
        for details in dataset_details_list
    ]

    agent = Step4()
    input_data = Step4Input(dataset_inputs=single_inputs)
    result = await agent.run(input_data)

    if not result.success:
        logger.error(f"Step 4 failed: {result.error_message}")
        # Return error results for all datasets
        return [
            {
                "dataset_input": details,
                "success": False,
                "dataset_details": None,
                "error_message": result.error_message,
            }
            for details in dataset_details_list
        ]

    # Convert Step4SingleResult to dicts for backward compatibility
    return [
        {
            "dataset_input": r.dataset_input,
            "success": r.success,
            "error_message": r.error_message,
            "dataset_details": r.dataset_details.model_dump()
            if r.dataset_details
            else None,
        }
        for r in result.outputs.results
    ]


# Legacy single-dataset wrapper for backward compatibility
async def step_4_single(dataset_details_json: str) -> Optional[dict]:
    """Add a single dataset to the database (legacy wrapper for backward compatibility)."""
    try:
        dataset_details = json.loads(dataset_details_json)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return None

    results = await step_4([dataset_details])
    if results and results[0]["success"]:
        return results[0]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add datasets to the database.")
    # New: ArXiv ID parameter to read from step_3 output
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper (reads datasets from step_3 output)",
        default=None,
    )
    parser.add_argument(
        "--dataset_details",
        type=str,
        help="[Backward compatibility] JSON string containing dataset details (name, description, etc.).",
        default=None,
    )
    args = parser.parse_args()

    async def main():
        # Mode 1: Read from step_3 output (NEW - PREFERRED)
        if args.arxiv_id:
            arxiv_id = args.arxiv_id
            print(f"Reading datasets from step_3 output for ArXiv ID: {arxiv_id}")

            try:
                datasets_to_add = read_step_3_output(arxiv_id)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                return []

            if not datasets_to_add:
                print("No datasets to add (none were successfully gathered in step 3)")
                write_step_4_output(arxiv_id, [])
                return []

            print(f"Processing {len(datasets_to_add)} datasets to add to database...")
            for idx, dataset in enumerate(datasets_to_add, 1):
                print(f"  {idx}. {dataset.get('name', 'Unknown')}")

            # Process all datasets in parallel
            results = await step_4(datasets_to_add)

            # Write the results to step_4.json
            write_step_4_output(arxiv_id, results)

            # Print summary
            print("\n" + "=" * 50)
            print("RESULTS SUMMARY:")
            print("=" * 50)
            success_count = sum(1 for r in results if r.get("success"))
            print(
                f"Successfully added {success_count}/{len(results)} datasets to database\n"
            )
            for idx, result in enumerate(results, 1):
                dataset_name = result.get("dataset_input", {}).get("name", "Unknown")
                status = "✓" if result.get("success") else "✗"
                print(f"{idx}. {status} {dataset_name}")
                if result.get("success") and result.get("dataset_details"):
                    details = result["dataset_details"]
                    print(
                        f"   → Added as: {details.get('name', 'N/A')} (ID: {details.get('id', 'N/A')})"
                    )
                elif result.get("error_message"):
                    print(f"   Error: {result['error_message']}")
            print("=" * 50)

            return results

        # Mode 2: Single dataset (backward compatibility)
        elif args.dataset_details:
            print("Adding single dataset...")
            result = await step_4_single(args.dataset_details)

            if result:
                print("\n" + "=" * 50)
                print("RESULT:")
                print("=" * 50)
                print(json.dumps(result, indent=2))
            else:
                print("\nFailed to add dataset")

            return [result] if result else []
        else:
            parser.error("Must provide either --arxiv_id or --dataset_details")

    # Run main function
    result = asyncio.run(main())
    if not result:
        print("\nNo results received")


# Workflow integration
class Step4WorkflowStep:
    """Workflow step wrapper for Step4."""

    name = "Step4WorkflowStep"

    def __init__(self):
        self.step = Step4()
        self.project_root = Path(__file__).resolve().parents[1]

    async def execute(self, state):
        """
        Execute Step4 using data from workflow state.

        Reads from state.data:
        - step_3_results: list of gathered information from step 3

        Writes to state.data:
        - step_4_results: list of dataset addition results
        """
        from extract_evaluation_results.step_base import StepResult

        # Get datasets from step 3 that need to be added
        step_3_results = state.data.get("step_3_results", [])

        # Get the main paper's arxiv_id for context
        main_paper_arxiv_id = state.arxiv_id

        # Build list of datasets to add
        # CRITICAL: Only process datasets that step_2 confirmed don't exist
        step_2_results = state.data.get("step_2_results", [])

        # Build a set of dataset names that were found in step_2
        found_dataset_names = set()
        for step_2_result in step_2_results:
            if step_2_result.get("found"):
                dataset_name = step_2_result.get("dataset_input", {}).get(
                    "dataset_name", ""
                )
                if dataset_name:
                    found_dataset_names.add(dataset_name.lower().strip())
                    found_dataset_names.add(_sanitize_dataset_name(dataset_name))

        datasets_to_add = []
        for step_3_result in step_3_results:
            if step_3_result.get("success"):
                dataset_input = step_3_result.get("dataset_input", {})
                dataset_info = step_3_result.get("information", {})

                dataset_name = dataset_input.get("dataset_name", "")
                sanitized_name = _sanitize_dataset_name(dataset_name)

                # CRITICAL: Only add datasets that step_2 confirmed don't exist
                # If step_2 found it, skip it (it already exists)
                if (
                    dataset_name.lower().strip() in found_dataset_names
                    or sanitized_name in found_dataset_names
                ):
                    logger.info(
                        f"Skipping {dataset_name} - already found in step_2, should not be added"
                    )
                    continue

                # Combine input and gathered information
                combined = {
                    "name": dataset_name,
                    "dataset_info": dataset_input.get("dataset_info"),
                    "paper_arxiv_id": main_paper_arxiv_id,  # Use main paper for context
                    "paper_title": dataset_input.get("paper_title"),
                    "description": dataset_info.get("description"),
                    "full_name": dataset_info.get("full_name"),
                    "hf_url": dataset_info.get("hf_url"),
                    "conference_url": dataset_info.get("conference_url"),
                    "arxiv_id": dataset_info.get(
                        "arxiv_id"
                    ),  # Dataset's own arxiv_id if it introduced the dataset
                }
                datasets_to_add.append(combined)

        logger.info(f"Step4: Adding {len(datasets_to_add)} datasets to DB")

        # If no datasets need to be added, return an empty result set
        target_dir = get_output_dir(state.arxiv_id)
        step4_path = target_dir / "step_4.json"

        if not datasets_to_add:

            class Step4RenamedOutput(BaseModel):
                step_4_results: list

            return StepResult(
                success=True,
                outputs=Step4RenamedOutput(step_4_results=[]),
            )

        # Run step_4.py in an isolated subprocess so that cancellation scopes from the agent
        # do not interfere with the main workflow coroutine.
        cmd = [
            sys.executable,
            "extract_evaluation_results/step_4.py",
            "--arxiv_id",
            state.arxiv_id,
        ]
        subprocess.run(cmd, check=True, cwd=self.project_root)

        step4_data = json.loads(step4_path.read_text()) if step4_path.exists() else []

        class Step4RenamedOutput(BaseModel):
            step_4_results: list

        return StepResult(
            success=True,
            outputs=Step4RenamedOutput(step_4_results=step4_data),
        )
