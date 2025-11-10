"""
This script defines an agent that can add datasets to the SQL database. It also links the datasets to the appropriate tasks.

**Key Feature**: This step processes all datasets in parallel internally, running multiple agent
instances concurrently for improved performance.

You can run it like so:

```bash
# Process datasets from step_3 output (reads from standardized location)
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --arxiv_id "2406.09414"

# Or add a single dataset directly
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --dataset_details "{\"name\": \"COCO\", \"description\": \"COCO is a large-scale object detection, segmentation, and captioning dataset.\", \"task_ids\": [2]}"
```
"""

import argparse
import asyncio
import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.utils import get_paper_details, get_formatted_tasks_list
from extract_evaluation_results.tools import (
    add_dataset,
    get_tasks_by_area,
)

logger = logging.getLogger(__name__)


class DatasetDetails(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    task_ids: list[int]
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


class Step4Output(BaseModel):
    """Output from Step 4: Dataset Adder - handles multiple datasets."""

    results: list[Step4SingleResult]


dataset_adder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI).

You are an expert in managing datasets in the SQL database of Hugging Face's leaderboards project. Your responsibility includes
adding new datasets to the database with comprehensive information when requested.

A colleague of yours has extracted evaluation results from an ArXiv paper and identified a particular dataset mentioned in the evaluation results which is not yet added to the SQL database.
Your task is to add this dataset to the database.
Another colleague of yours has fetched the paper details from the web/Hugging Faceand will provide you with the required information.

## Important notes

**CRITICAL**: Every dataset MUST be linked to EXACTLY ONE task. Do NOT link datasets to multiple tasks unless the dataset is truly exceptional (like ImageNet which genuinely serves multiple distinct purposes).

Ensure you provide all relevant information including:
- name (required): The name of the dataset
- description (required): A description of what the dataset contains and its purpose
- task_ids (required): List containing EXACTLY ONE task ID (e.g., [1] for Image Classification)
  **CRITICAL**: Choose the SINGLE most appropriate task based on the dataset's PRIMARY purpose and description, NOT from the paper's tasks.

  **Task Selection Guidelines**:
  - For math/reasoning datasets (e.g., AIME, GPQA, MMLU) → use "Language Modeling"
  - For vision-only datasets (e.g., Oxford-IIIT Pets) → use "Image Classification" or other Computer Vision tasks
  - For speech/audio datasets → use "Automatic Speech Recognition" or "Audio Classification" or other Speech/Audio tasks
  - For video-language datasets (e.g., LVBench, MLVU, MVBench) → use "Video-Language Models"
  - For vision-language datasets (e.g., MMMU, AI2D) → use "Vision-Language Models"
  - For audio-language datasets (e.g., MuchoMusic, OpenAudioBench) → use "Audio-Language Models"
  - For "Omni" datasets that involve multiple modalities (e.g., OmniBench, Daily-Omni, Video-Holmes, WorldSense) → use "Omni models"
  - For robotics datasets (e.g., CALVIN, LIBERO, Meta-World) → use "Robotics"
  - For OCR datasets → use "OCR"
  - **If no specific task fits**: Use the "other" task (find it by calling get_tasks_by_area("Other") and look for the task named "other"). This is a valid fallback option for datasets that don't clearly fit into any of the standard categories.
  - Only use suggested_task_ids if they genuinely match the dataset's PRIMARY purpose

  **Examples of correct single-task linking**:
  - LVBench → task_ids=[Video-Language Models task ID]
  - MMLU → task_ids=[Language Modeling task ID]
  - Oxford-IIIT Pets → task_ids=[Image Classification task ID]
  - OmniBench → task_ids=[Omni models task ID]
  - MMMU → task_ids=[Vision-Language Models task ID]
  - CALVIN → task_ids=[Robotics task ID]

- full_name (optional): The full name of the dataset
- url (optional): Main URL for the dataset
- hf_url (optional): Hugging Face dataset URL
- paper_url (optional): URL to the paper that introduced this dataset

{tasks_list}

## Finding and Linking Tasks

Use get_tasks_by_area to search for tasks by research area (e.g., "Robotics", "Computer Vision", "NLP", "Other", ...).
This helps you find appropriate task IDs when you're not sure which task applies to a dataset.

**Using the "other" task as fallback**:
If you cannot find a specific task that matches the dataset's purpose after searching through relevant areas, use the "other" task as a fallback:
1. Call get_tasks_by_area("Other") to find tasks in the "Other" area
2. Look for the task named "other" in the results
3. Use that task ID when adding the dataset

Example workflow for specific tasks:
1. Call get_tasks_by_area("Computer Vision") to find Computer Vision task IDs
2. Call the `add_dataset` tool to add the dataset to the database with task_ids=[task_id] (single task ID in a list)

Example workflow for fallback to "other":
1. Search relevant areas but find no good match
2. Call get_tasks_by_area("Other") to find the "other" task
3. Call the `add_dataset` tool with task_ids=[other_task_id] (the "other" task ID)

Example: To add the COCO dataset for Object Detection, use task_ids=[2] (single task)
Example: To add Oxford-IIIT Pets for Image Classification, use task_ids=[1] (single task)
Example: To add LVBench for Video-Language Models, use task_ids=[Video-Language Models task ID] (single task)
Example: To add MMLU for Language Modeling, use task_ids=[Language Modeling task ID] (single task)
Example: To add OmniBench for Omni models, use task_ids=[Omni models task ID] (single task)
Example: To add a dataset that doesn't fit any standard category, use task_ids=[other_task_id] (the "other" task from the "Other" area)

**Note**: Only in extremely rare cases (like ImageNet which genuinely serves multiple distinct purposes) should you link to multiple tasks. For 99% of datasets, choose the single most appropriate task. If no specific task fits, use the "other" task rather than forcing an incorrect match.

## Output format

When a dataset is added successfully, return the details of the dataset in the following Pydantic model:
```python
class DatasetDetails(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    task_ids: list[int]
    hf_url: Optional[str] = None
    paper_url: Optional[str] = None


class Response(BaseModel):
    dataset_successfully_added: bool
    dataset_details: Optional[DatasetDetails] = None # Only complete this if dataset_successfully_added is True
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
            return Step4SingleResult(
                dataset_input={"error": "Invalid JSON"},
                success=False,
                dataset_details=None,
                error_message=f"Invalid JSON in dataset_details: {e}",
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

        except Exception as e:
            print(f"Error adding dataset '{dataset_name}': {str(e)}")
            return Step4SingleResult(
                dataset_input=dataset_details,
                success=False,
                dataset_details=None,
                error_message=f"Error during addition: {str(e)}",
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
                from extract_evaluation_results.step_base import StepResult

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

            # Process all datasets in parallel
            tasks = [
                self._process_single_dataset(
                    dataset_input=dataset_input,
                    formatted_instructions=formatted_instructions,
                )
                for dataset_input in inputs.dataset_inputs
            ]

            # Use gather with return_exceptions to prevent cancellation propagation
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if any tasks were cancelled or raised exceptions
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, asyncio.CancelledError):
                    logger.warning(f"Task {i} was cancelled")
                    # Create a failed result for this dataset
                    successful_results.append(
                        Step4SingleResult(
                            dataset_input={},
                            success=False,
                            dataset_details=None,
                            error_message="Task was cancelled",
                        )
                    )
                elif isinstance(result, Exception):
                    logger.error(f"Task {i} raised exception: {result}")
                    successful_results.append(
                        Step4SingleResult(
                            dataset_input={},
                            success=False,
                            dataset_details=None,
                            error_message=str(result),
                        )
                    )
                else:
                    successful_results.append(result)

            # Return successful result with all findings
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=True,
                outputs=Step4Output(results=successful_results),
                error_message=None,
            )

        except asyncio.CancelledError:
            # Handle cancellation gracefully
            logger.warning("Step 4 was cancelled, cleaning up...")
            await self._cleanup_mcp_servers()
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=False, outputs=None, error_message="Step 4 was cancelled"
            )
        except Exception as e:
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=False, outputs=None, error_message=f"Step 4 failed: {str(e)}"
            )
        finally:
            # Always cleanup MCP servers
            await self._cleanup_mcp_servers()

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

    # Extract datasets that were successfully gathered
    datasets_to_add = []
    for item in step_3_data:
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
                # Note: task_ids will be inferred by the agent
                "task_ids": [],  # Agent will determine appropriate task IDs
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
            - task_ids: List of task IDs (required)
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

    # result.outputs is now a Step4Output model with a list of Step4SingleResult
    # Convert to list of dicts for backward compatibility
    output_list = []
    for single_result in result.outputs.results:
        output_dict = {
            "dataset_input": single_result.dataset_input,
            "success": single_result.success,
            "error_message": single_result.error_message,
        }
        if single_result.dataset_details:
            output_dict["dataset_details"] = single_result.dataset_details.model_dump()
        else:
            output_dict["dataset_details"] = None
        output_list.append(output_dict)

    return output_list


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
        help="[Backward compatibility] JSON string containing dataset details (name, description, task_ids, etc.).",
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

        # Get the main paper's arxiv_id and tasks for context
        main_paper_arxiv_id = state.arxiv_id

        # Fetch the main paper's tasks to suggest as default task_ids for datasets
        main_paper_task_ids = []
        try:
            from backend.database.connection import db_manager
            from backend.models.database import Paper

            with db_manager.session_local() as db:
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == main_paper_arxiv_id)
                    .first()
                )
                if paper and paper.tasks:
                    main_paper_task_ids = [task.id for task in paper.tasks]
                    logger.info(f"Main paper tasks: {main_paper_task_ids}")
        except Exception as e:
            logger.warning(f"Could not fetch main paper tasks: {e}")

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
                    # Also check sanitized version
                    sanitized = (
                        dataset_name.replace("→", " to ")
                        .replace("(", " ")
                        .replace(")", "")
                        .replace("[", " ")
                        .replace("]", "")
                        .lower()
                        .strip()
                    )
                    found_dataset_names.add(sanitized)

        datasets_to_add = []
        for step_3_result in step_3_results:
            if step_3_result.get("success"):
                dataset_input = step_3_result.get("dataset_input", {})
                dataset_info = step_3_result.get("information", {})

                # Sanitize dataset name to remove problematic characters
                dataset_name = dataset_input.get("dataset_name", "")
                # Replace special characters that might cause issues with JSON/agent processing
                # Remove all parentheses, brackets, and arrows to simplify
                sanitized_name = (
                    dataset_name.replace("→", " to ")
                    .replace("(", " ")
                    .replace(")", "")
                    .replace("[", " ")
                    .replace("]", "")
                )

                # CRITICAL: Only add datasets that step_2 confirmed don't exist
                # If step_2 found it, skip it (it already exists with correct task associations)
                if (
                    dataset_name.lower().strip() in found_dataset_names
                    or sanitized_name.lower().strip() in found_dataset_names
                ):
                    logger.info(
                        f"Skipping {dataset_name} - already found in step_2, should not be added"
                    )
                    continue

                # Combine input and gathered information
                # IMPORTANT: Do NOT pre-fill task_ids with paper's tasks
                # Let the agent infer appropriate tasks based on dataset description
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
                    # Do NOT pre-fill task_ids - let agent infer based on dataset purpose
                    # Only provide paper's tasks as context/hint, not as requirement
                    "suggested_task_ids": main_paper_task_ids
                    if main_paper_task_ids
                    else [],
                }
                datasets_to_add.append(combined)

        logger.info(f"Step4: Adding {len(datasets_to_add)} datasets to DB")

        # Build inputs from state.data - convert dictionaries to Step4SingleInput format
        formatted_inputs = [
            {"dataset_details_json": json.dumps(dataset)} for dataset in datasets_to_add
        ]
        inputs = {"dataset_inputs": formatted_inputs}

        # Execute the step
        result = await self.step.run(inputs)

        # Rename 'results' to 'step_4_results' to avoid collision with other steps
        if result.success and result.outputs:
            from extract_evaluation_results.step_base import StepResult

            output_dict = result.outputs.model_dump()
            # Rename the key
            if "results" in output_dict:
                output_dict["step_4_results"] = output_dict.pop("results")

            # Create new output model with renamed field
            from pydantic import BaseModel

            class Step4RenamedOutput(BaseModel):
                step_4_results: list

            renamed_output = Step4RenamedOutput(
                step_4_results=output_dict["step_4_results"]
            )

            return StepResult(
                success=True, outputs=renamed_output, reasoning=result.reasoning
            )

        return result
