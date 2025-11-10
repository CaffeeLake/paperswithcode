"""
This script defines an agent that can gather information about datasets.

It uses the Exa AI MCP server and Hugging Face MCP server to search the web/HF for information about the datasets.

To use the Hugging Face MCP server, you need to add your Hugging Face API token to backend/keys.env:
  HF_TOKEN=hf_your_token_here

You can generate a token at: https://huggingface.co/settings/tokens

This script is typically used after step_2.py fails to find datasets in the database.
It takes the dataset_details extracted from step_1.py and gathers additional information
about the datasets from the web and Hugging Face.

**Key Feature**: This step processes all datasets in parallel internally, running multiple agent
instances concurrently for improved performance.

You can run it like so:

```bash
# Process datasets from step_2 output (reads from standardized location)
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --arxiv_id "2406.09414"

# Using dataset_details JSON (recommended for single dataset)
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --dataset_details '{"dataset_name": "COCO", "dataset_info": "...", "paper_arxiv_id": "1405.0312"}'

# Or read from a file
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --dataset_details_file step_1_output.json
```

For backward compatibility, you can still use individual parameters:
```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --dataset_name "COCO"
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --arxiv_id "2103.00020"
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --hf_url "huggingface.co/datasets/imagenet-1k"
```
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.utils import get_paper_details, get_formatted_tasks_list
from extract_evaluation_results.tools import get_tasks_by_area

logger = logging.getLogger(__name__)


class DatasetInformation(BaseModel):
    description: str
    full_name: str
    task_id: int
    hf_url: Optional[str] = None
    conference_url: Optional[str] = None
    arxiv_id: Optional[str] = None


dataset_information_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), titled the PapersWithCode project. This way, people can track progress of state-of-the-art models over time.

## Task

A colleague of yours has extracted evaluation results from an ArXiv paper and identified a particular dataset mentioned in the evaluation results.
This dataset is not yet added to the SQL database of Hugging Face's project.
You will be given some context about this dataset based on the paper, and your task is to gather comprehensive information about this dataset by searching the web and Hugging Face,
so that it can be added to the SQL database.

You will be provided with:
- The dataset name (as mentioned in the paper)
- Any information about the dataset that was extracted from the paper
- Potentially the title of the paper that introduced the dataset, as found in the citation section at the end of the paper
- Potentially the ArXiv ID of the paper that introduced the dataset, as found in the citation section at the end of the paper

You need to find the following information about the dataset:
- A comprehensive description of the dataset
- The full name of the dataset
- The task_id (REQUIRED): The ID of the SINGLE most appropriate task this dataset should be linked to. You MUST determine this - use the "Other" task as fallback if no specific task matches.
- The Hugging Face URL of the dataset, if available
- The ArXiv ID of the paper that introduced the dataset, if available (e.g., "2103.00020")
- The conference URL of the dataset, if available (e.g., "https://openaccess.thecvf.com/CVPR2021/papers/Kolesnikov_Decoupled_Attention_Network_for_Vision-Language_Tasks_CVPR_2021_paper.pdf")

Use the provided dataset information as context, but verify and expand on it using web search and Hugging Face.

Strategy: Start with 2-3 focused searches to gather core information, then refine if needed. Prioritize finding the description, full_name, task_id, and at least one URL (HF or ArXiv).
**IMPORTANT CONSTRAINT**: You have a maximum of 15 turns. Be efficient with your tool calls and prioritize the most essential information.

## Task Selection (CRITICAL)

**CRITICAL**: Every dataset MUST be linked to EXACTLY ONE task. You MUST determine the appropriate task_id as part of gathering information. Do NOT link datasets to multiple tasks unless the dataset is truly exceptional (like ImageNet which genuinely serves multiple distinct purposes).

**Task Selection Guidelines**:
- For math/reasoning datasets (e.g., AIME, GPQA, MMLU) → use "Language Modeling"
- For vision-only datasets (e.g., Oxford-IIIT Pets) → use "Image Classification" or other Computer Vision tasks
- For video classification/action recognition datasets (e.g., Kinetics-400, Something-Something V2, UCF101, HMDB-51) → use "Image Classification" (video classification is similar to image classification but for video frames)
- For speech/audio datasets → use "Automatic Speech Recognition" or "Audio Classification" or other Speech/Audio tasks
- For video-language datasets (e.g., LVBench, MLVU, MVBench) → use "Video-Language Models"
- For vision-language datasets (e.g., MMMU, AI2D) → use "Vision-Language Models"
- For audio-language datasets (e.g., MuchoMusic, OpenAudioBench) → use "Audio-Language Models"
- For "Omni" datasets that involve multiple modalities (e.g., OmniBench, Daily-Omni, Video-Holmes, WorldSense) → use "Omni models"
- For robotics datasets (e.g., CALVIN, LIBERO, Meta-World) → use "Robotics"
- For OCR datasets → use "OCR"
- **If no specific task fits**: Use the "other" task (find it by calling get_tasks_by_area("Other") and look for the task named "other"). This is a valid fallback option for datasets that don't clearly fit into any of the standard categories.

**Examples of correct single-task linking**:
- LVBench → task_id=[Video-Language Models task ID]
- MMLU → task_id=[Language Modeling task ID]
- Oxford-IIIT Pets → task_id=[Image Classification task ID]
- Kinetics-400 → task_id=[Image Classification task ID] (video classification)
- UCF101 → task_id=[Image Classification task ID] (video classification)
- Something-Something V2 → task_id=[Image Classification task ID] (video classification)
- OmniBench → task_id=[Omni models task ID]
- MMMU → task_id=[Vision-Language Models task ID]
- CALVIN → task_id=[Robotics task ID]

## Finding and Linking Tasks

Use get_tasks_by_area to search for tasks by research area (e.g., "Robotics", "Computer Vision", "NLP", "Other", ...).
This helps you find appropriate task IDs when you're not sure which task applies to a dataset.

**Using the "other" task as fallback**:
If you cannot find a specific task that matches the dataset's purpose after searching through relevant areas, use the "other" task as a fallback:
1. Call get_tasks_by_area("Other") to find tasks in the "Other" area
2. Look for the task named "other" in the results
3. Use that task ID as the task_id

Example workflow for specific tasks:
1. Call get_tasks_by_area("Computer Vision") to find Computer Vision task IDs
2. Select the most appropriate task_id based on the dataset's PRIMARY purpose

Example workflow for fallback to "other":
1. Search relevant areas but find no good match
2. Call get_tasks_by_area("Other") to find the "other" task
3. Use that task ID as the task_id

**Note**: Only in extremely rare cases (like ImageNet which genuinely serves multiple distinct purposes) should you link to multiple tasks.
For 99% of datasets, choose the single most appropriate task. If no specific task fits, use the "other" task rather than forcing an incorrect match.
You MUST always provide a task_id - it is a required field.

## Context: Available Tasks and Datasets

Below is a list of machine learning tasks currently in the database along with their associated datasets. This provides context about the current information landscape of the PapersWithCode project:

{tasks_list}

Use this context to better understand which tasks are available and which datasets are commonly used for each task. This helps you determine the appropriate task_id for the dataset.

## Output format
```python
from pydantic import BaseModel

class DatasetInformation(BaseModel):
    description: str
    full_name: str
    task_id: int
    hf_url: Optional[str] = None
    conference_url: Optional[str] = None
    arxiv_id: Optional[str] = None
```

Return the information as a JSON string.
Do not make up information, only use the information provided in the web search and Hugging Face.
Gather the essential information efficiently - prioritize quality over exhaustive searches.
You MUST always include the task_id field - it is required.
"""


class Step3SingleInput(BaseModel):
    """Input data for a single dataset in Step3."""

    dataset_name: Optional[str] = None
    arxiv_id: Optional[str] = None
    dataset_info: Optional[str] = None
    paper_title: Optional[str] = None


class Step3Input(BaseModel):
    """Input data for Step3 - handles multiple datasets."""

    dataset_inputs: list[Step3SingleInput]


class Step3SingleResult(BaseModel):
    """Result for a single dataset information gathering."""

    dataset_input: Step3SingleInput
    success: bool
    information: Optional[DatasetInformation] = None
    error_message: Optional[str] = None


class Step3Output(BaseModel):
    """Output data for Step3 - handles multiple datasets."""

    results: list[Step3SingleResult]


class Step3(AgentStep[Step3Input, Step3Output]):
    """Agent-based step for gathering dataset information from web and HF."""

    input_model = Step3Input
    output_model = Step3Output

    def __init__(self):
        super().__init__(
            name="Step3: Dataset Information Gatherer",
            description="Gathers information about datasets from the web and Hugging Face",
            instructions=dataset_information_prompt,
            tools=[get_tasks_by_area],  # Added get_tasks_by_area for task selection
            agent_output_type=DatasetInformation,
            model="gpt-5-mini",
            mcp_servers=["exa", "huggingface"],  # Exa required, HF optional
        )

    async def _process_single_dataset(
        self, dataset_input: Step3SingleInput, formatted_instructions: str
    ) -> Step3SingleResult:
        """
        Process a single dataset through the agent.

        Args:
            dataset_input: Single dataset input data
            formatted_instructions: Pre-formatted instructions with tasks list

        Returns:
            Step3SingleResult with gathered information
        """
        dataset_name = dataset_input.dataset_name or "Unknown"

        try:
            # Build search parts
            search_parts = []
            if dataset_input.dataset_name:
                search_parts.append(f"Dataset name: '{dataset_input.dataset_name}'")
            if dataset_input.arxiv_id:
                search_parts.append(f"ArXiv ID: '{dataset_input.arxiv_id}'")

            if not search_parts:
                return Step3SingleResult(
                    dataset_input=dataset_input,
                    success=False,
                    information=None,
                    error_message="At least one search parameter must be provided",
                )

            search_str = " and ".join(search_parts)

            # Build the prompt with dataset information
            prompt_parts = [
                f"Gather information about the following dataset: {search_str}"
            ]

            # Fetch and include paper details if arxiv_id is available
            if dataset_input.arxiv_id:
                try:
                    paper_details = await get_paper_details(dataset_input.arxiv_id)
                    prompt_parts.append("\n## Paper details")
                    prompt_parts.append(paper_details)
                except Exception as e:
                    logger.warning(
                        f"Could not fetch paper details for {dataset_input.arxiv_id}: {e}"
                    )
                    # Fallback to just title if available
                    if dataset_input.paper_title:
                        prompt_parts.append("\n## Paper that introduced the dataset:")
                        prompt_parts.append(f"Title: {dataset_input.paper_title}")
            elif dataset_input.paper_title:
                prompt_parts.append("\n## Paper that introduced the dataset:")
                prompt_parts.append(f"Title: {dataset_input.paper_title}")

            if dataset_input.dataset_info:
                prompt_parts.append("\n## Information extracted from the paper:")
                prompt_parts.append(f"{dataset_input.dataset_info}")

            prompt = "\n".join(prompt_parts)

            # Run the agent for this dataset
            print(f"Gathering information for dataset: {dataset_name}")
            agent_response = await self._run_agent(prompt, formatted_instructions)

            # Process the agent output
            if isinstance(agent_response, DatasetInformation):
                print(f"✓ Gathered information for: {dataset_name}")
                return Step3SingleResult(
                    dataset_input=dataset_input,
                    success=True,
                    information=agent_response,
                    error_message=None,
                )
            else:
                raise ValueError(
                    f"Unexpected agent output type: {type(agent_response)}"
                )

        except Exception as e:
            print(f"Error gathering information for dataset '{dataset_name}': {str(e)}")
            return Step3SingleResult(
                dataset_input=dataset_input,
                success=False,
                information=None,
                error_message=f"Error during information gathering: {str(e)}",
            )

    async def run(self, inputs):
        """
        Override run to handle parallel processing of multiple datasets.
        """
        # Validate inputs if dict provided
        if isinstance(inputs, dict):
            try:
                inputs = Step3Input(**inputs)
            except Exception as e:
                from extract_evaluation_results.step_base import StepResult

                return StepResult(
                    success=False,
                    error_message=f"Input validation failed: {e}",
                    outputs=None,
                )

        try:
            # Set up MCP servers BEFORE parallel processing
            # This ensures they're set up in the main task context
            if self._mcp_servers is None:
                self._mcp_servers = await self._setup_mcp_servers()

            # Format instructions once (same for all datasets)
            tasks_list = get_formatted_tasks_list()
            formatted_instructions = self.instructions.format(tasks_list=tasks_list)

            # Process all datasets in parallel
            tasks = [
                self._process_single_dataset(
                    dataset_input=dataset_input,
                    formatted_instructions=formatted_instructions,
                )
                for dataset_input in inputs.dataset_inputs
            ]

            results = await asyncio.gather(*tasks)

            # Return successful result with all findings
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=True,
                outputs=Step3Output(results=list(results)),
                error_message=None,
            )

        except Exception as e:
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=False, outputs=None, error_message=f"Step 3 failed: {str(e)}"
            )
        finally:
            # Clean up MCP servers (in the same task context they were set up)
            # Suppress any cleanup errors as they're non-critical
            try:
                await self._cleanup_mcp_servers()
            except Exception as e:
                self.logger.debug(f"MCP server cleanup error (non-critical): {e}")

    async def build_agent_prompt(self, inputs: Step3Input) -> str:
        """
        Not used in the new parallel implementation.
        Kept for compatibility with base class signature.
        """
        raise NotImplementedError("Use _process_single_dataset instead")

    async def format_instructions(self, inputs: Step3Input) -> str:
        """
        Format instructions with paper-specific context.
        """
        # Format instructions with tasks list
        tasks_list = get_formatted_tasks_list()

        # Format instructions with context
        return self.instructions.format(
            tasks_list=tasks_list,
        )


def get_output_dir(arxiv_id: str) -> Path:
    """Get the output directory for a given arxiv_id.

    Returns: backend/outputs/evaluation_results/{arxiv_id}
    """
    output_dir = Path(__file__).parent.parent / "backend" / "outputs"
    eval_results_dir = output_dir / "evaluation_results" / arxiv_id
    eval_results_dir.mkdir(parents=True, exist_ok=True)
    return eval_results_dir


def read_step_2_output(arxiv_id: str) -> list[dict]:
    """Read the step_2 output JSON file and extract datasets that were not found.

    Reads from: backend/outputs/evaluation_results/{arxiv_id}/step_2.json

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        List of dataset_input dicts for datasets that were not found in step 2
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_2.json"

    if not json_file.exists():
        raise FileNotFoundError(
            f"Could not find step_2 output file: {json_file}. "
            f"Run step_2.py first to generate the output."
        )

    with open(json_file, "r") as f:
        step_2_data = json.load(f)

    # Extract datasets that were not found in step 2
    not_found_datasets = []
    for item in step_2_data:
        if not item.get("success", False):
            # Get the original dataset detail from step_1
            dataset_detail = item.get("dataset", {})
            # Convert to Step3 input format
            dataset_input = {
                "dataset_name": dataset_detail.get("dataset_name"),
                "arxiv_id": dataset_detail.get("paper_arxiv_id"),
                "dataset_info": dataset_detail.get("dataset_info"),
                "paper_title": dataset_detail.get("paper_title"),
            }
            not_found_datasets.append(dataset_input)

    return not_found_datasets


def write_step_3_output(arxiv_id: str, results: list[dict]) -> None:
    """Write the step_3 output JSON file to the standardized location.

    Writes to: backend/outputs/evaluation_results/{arxiv_id}/step_3.json

    Args:
        arxiv_id: The ArXiv ID of the paper
        results: List of result dicts from step_3
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_3.json"

    json_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"✓ Step 3 output written to: {json_file}")


def parse_dataset_details(dataset_details_input: str) -> dict:
    """Parse dataset_details from JSON string or file path."""
    # Try to parse as JSON string first
    try:
        return json.loads(dataset_details_input)
    except json.JSONDecodeError:
        # If not valid JSON, try as file path
        file_path = Path(dataset_details_input)

        # Check in backend/outputs first, then extract_evaluation_results directory
        if not file_path.exists():
            output_dir = Path(__file__).parent.parent / "backend" / "outputs"
            potential_path = output_dir / dataset_details_input
            if potential_path.exists():
                file_path = potential_path

        # Also check in extract_evaluation_results directory
        if not file_path.exists():
            extract_dir = Path(__file__).parent
            potential_path = extract_dir / dataset_details_input
            if potential_path.exists():
                file_path = potential_path

        if file_path.exists():
            with open(file_path, "r") as f:
                content = f.read()
                # Try to parse as JSON
                try:
                    data = json.loads(content)
                    # If it's the full step_1 response, extract first dataset_detail
                    if "dataset_details" in data and isinstance(
                        data["dataset_details"], list
                    ):
                        if data["dataset_details"]:
                            return data["dataset_details"][0]
                        else:
                            raise ValueError("dataset_details list is empty")
                    # Otherwise assume it's already a dataset_detail dict
                    return data
                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse JSON from file: {file_path}")
        else:
            raise ValueError(
                f"Could not parse as JSON string or find file: {dataset_details_input}"
            )


async def step_3(
    dataset_inputs: list[dict],
) -> list[dict]:
    """Gather information about multiple datasets from the web and Hugging Face (wrapper for Step3).

    Args:
        dataset_inputs: List of dataset input dictionaries, each containing:
            - dataset_name (optional): Name of the dataset
            - arxiv_id (optional): ArXiv ID of the paper that introduced the dataset
            - dataset_info (optional): Additional information about the dataset
            - paper_title (optional): Title of the paper that introduced the dataset

    Returns:
        List of dictionaries, each with 'dataset_input', 'success', 'information', and 'error_message' keys
    """
    # Convert dicts to Step3SingleInput models
    single_inputs = [Step3SingleInput(**input_dict) for input_dict in dataset_inputs]

    agent = Step3()
    input_data = Step3Input(dataset_inputs=single_inputs)
    result = await agent.run(input_data)

    if not result.success:
        logger.error(f"Step 3 failed: {result.error_message}")
        # Return error results for all datasets
        return [
            {
                "dataset_input": input_dict,
                "success": False,
                "information": None,
                "error_message": result.error_message,
            }
            for input_dict in dataset_inputs
        ]

    # result.outputs is now a Step3Output model with a list of Step3SingleResult
    # Convert to list of dicts for backward compatibility
    output_list = []
    for single_result in result.outputs.results:
        output_dict = {
            "dataset_input": single_result.dataset_input.model_dump(),
            "success": single_result.success,
            "error_message": single_result.error_message,
        }
        if single_result.information:
            output_dict["information"] = single_result.information.model_dump()
        else:
            output_dict["information"] = None
        output_list.append(output_dict)

    return output_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gather information about datasets from the web and Hugging Face."
    )
    # New: ArXiv ID parameter to read from step_2 output
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper (reads datasets from step_2 output)",
        default=None,
    )
    parser.add_argument(
        "--dataset_details",
        type=str,
        help="JSON string containing dataset_details (dataset_name, dataset_info, paper_title, paper_arxiv_id).",
        default=None,
    )
    parser.add_argument(
        "--dataset_details_file",
        type=str,
        help="Path to JSON file containing dataset_details or step_1 output file.",
        default=None,
    )
    args = parser.parse_args()

    async def main():
        # Mode 1: Read from step_2 output
        if args.arxiv_id:
            arxiv_id = args.arxiv_id
            print(f"Reading datasets from step_2 output for ArXiv ID: {arxiv_id}")

            try:
                dataset_inputs = read_step_2_output(arxiv_id)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                return []

            if not dataset_inputs:
                print(
                    "No datasets to gather information for (all were found in step 2)"
                )
                write_step_3_output(arxiv_id, [])
                return []

            print(f"Processing {len(dataset_inputs)} datasets not found in database...")
            for idx, dataset_input in enumerate(dataset_inputs, 1):
                print(f"  {idx}. {dataset_input.get('dataset_name', 'Unknown')}")

            # Process all datasets in parallel
            results = await step_3(dataset_inputs)

            # Write the results to step_3.json
            write_step_3_output(arxiv_id, results)

            # Print summary
            print("\n" + "=" * 50)
            print("RESULTS SUMMARY:")
            print("=" * 50)
            success_count = sum(1 for r in results if r.get("success"))
            print(
                f"Successfully gathered information for {success_count}/{len(results)} datasets\n"
            )
            for idx, result in enumerate(results, 1):
                dataset_name = result.get("dataset_input", {}).get(
                    "dataset_name", "Unknown"
                )
                status = "✓" if result.get("success") else "✗"
                print(f"{idx}. {status} {dataset_name}")
                if result.get("success") and result.get("information"):
                    info = result["information"]
                    print(f"   Full name: {info.get('full_name', 'N/A')}")
                    if info.get("hf_url"):
                        print(f"   HF URL: {info['hf_url']}")
                elif result.get("error_message"):
                    print(f"   Error: {result['error_message']}")
            print("=" * 50)

            return results

        # Mode 2: Parse dataset_details (single or from file)
        dataset_detail = None
        if args.dataset_details:
            dataset_detail = parse_dataset_details(args.dataset_details)
        elif args.dataset_details_file:
            dataset_detail = parse_dataset_details(args.dataset_details_file)

        # Extract values from dataset_detail
        if dataset_detail:
            dataset_input = {
                "dataset_name": dataset_detail.get("dataset_name"),
                "arxiv_id": dataset_detail.get("paper_arxiv_id"),
                "dataset_info": dataset_detail.get("dataset_info", ""),
                "paper_title": dataset_detail.get("paper_title"),
            }

        # Check if at least one search parameter is provided
        if not any(
            [
                dataset_input.get("dataset_name"),
                dataset_input.get("arxiv_id"),
            ]
        ):
            parser.error(
                "Must provide either --arxiv_id (to read from step_2 output) or "
                "--dataset_details/--dataset_details_file"
            )

        # Process single dataset (backward compatibility)
        print(
            f"Processing single dataset: {dataset_input.get('dataset_name', 'Unknown')}"
        )
        results = await step_3([dataset_input])

        if results and results[0]:
            result = results[0]
            print("\n" + "=" * 50)
            print("RESULT:")
            print("=" * 50)
            print(json.dumps(result, indent=2))

        return results

    # Run main function
    result = asyncio.run(main())
    if not result:
        print("\nNo results received")


# Legacy single-dataset wrapper for backward compatibility
async def step_3_single(
    dataset_name: Optional[str],
    arxiv_id: Optional[str],
    hf_url: Optional[str],
    dataset_info: Optional[str] = None,
    paper_title: Optional[str] = None,
) -> Optional[dict]:
    """Gather information about a single dataset (legacy wrapper for backward compatibility)."""
    input_dict = {
        "dataset_name": dataset_name,
        "arxiv_id": arxiv_id,
        "hf_url": hf_url,
        "dataset_info": dataset_info,
        "paper_title": paper_title,
    }
    results = await step_3([input_dict])
    if results and results[0]["success"]:
        return results[0]
    return None


# Workflow integration
class Step3WorkflowStep:
    """Workflow step wrapper for Step3."""

    name = "Step3WorkflowStep"

    def __init__(self):
        self.step = Step3()

    async def execute(self, state):
        """
        Execute Step3 using data from workflow state.

        Reads from state.data:
        - step_2_results: list of step 2 results (filters for not found datasets)
        - dataset_details: list of dataset details from step 1

        Writes to state.data:
        - step_3_results: list of gathered information results
        """
        from extract_evaluation_results.step_base import StepResult

        # Get datasets that were not found in step 2
        step_2_results = state.data.get("step_2_results", [])

        # Build list of datasets to process (those not found in DB)
        datasets_to_process = []
        for step_2_result in step_2_results:
            if not step_2_result.get("found"):
                # Get the original dataset detail from dataset_input
                dataset_input_data = step_2_result.get("dataset_input", {})
                dataset_input = {
                    "dataset_name": dataset_input_data.get("dataset_name"),
                    "arxiv_id": dataset_input_data.get("paper_arxiv_id"),
                    "dataset_info": dataset_input_data.get("dataset_info"),
                    "paper_title": dataset_input_data.get("paper_title"),
                }
                datasets_to_process.append(dataset_input)

        logger.info(
            f"Step3: Processing {len(datasets_to_process)} datasets not found in DB"
        )

        # Build inputs from state.data
        inputs = {"dataset_inputs": datasets_to_process}

        # Execute the step
        result = await self.step.run(inputs)

        # Rename 'results' to 'step_3_results' to avoid collision with Step2
        if result.success and result.outputs:
            from extract_evaluation_results.step_base import StepResult

            output_dict = result.outputs.model_dump()
            # Rename the key
            if "results" in output_dict:
                output_dict["step_3_results"] = output_dict.pop("results")

            # Create new output model with renamed field
            from pydantic import BaseModel

            class Step3RenamedOutput(BaseModel):
                step_3_results: list

            renamed_output = Step3RenamedOutput(
                step_3_results=output_dict["step_3_results"]
            )

            return StepResult(
                success=True, outputs=renamed_output, reasoning=result.reasoning
            )

        return result
