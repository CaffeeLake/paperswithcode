"""
This script uses an AI agent to find datasets in the database based on evaluation results extracted from a paper.

It reads the output from step_1 (which extracts evaluation results and dataset details from a paper)
and uses an AI agent to search for each mentioned dataset in the database. The agent uses multiple
search strategies including searching by dataset name, ArXiv ID of the introducing paper, and
Hugging Face URL. It can also use web search for disambiguation when needed.

**Key Feature**: This step processes all datasets in parallel internally, running multiple agent
instances concurrently for improved performance.

You can run it like so:

```bash
# Process a paper (reads step_1 output JSON file from standardized location)
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --arxiv_id "2406.09414"
```

The script will:
1. Read the step_1 output JSON file from backend/outputs/evaluation_results/{arxiv_id}/step_1.json
2. Process ALL datasets mentioned in the step_1 output IN PARALLEL
3. Use an AI agent to search for each dataset in the database using multiple strategies
4. Return the dataset information if found, or "Dataset not found" if not found for each dataset
5. Write results to step_2.json and pretty print a summary
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from agents import AgentOutputSchema

from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.utils import (
    get_paper_details,
    get_formatted_tasks_list,
)
from extract_evaluation_results.tools import find_dataset


class DatasetDetail(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    hf_url: str
    paper_url: str
    task_ids: list[int]


class Response(BaseModel):
    reasoning: str
    dataset_found: bool
    dataset_detail: Optional[DatasetDetail] = None


dataset_finder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape
by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI).
This way, people can track progress of state-of-the-art models over time.

You are an expert in managing machine learning (ML) datasets in the SQL database of Hugging Face's project used for benchmarking ML models.

## Task

A colleague of yours has extracted evaluation results from an ArXiv paper and identified a particular dataset mentioned in the evaluation results.
Your task is to determine whether this dataset already exists in the SQL database or not.

## Context: Available Machine Learning Areas, Tasks and Datasets

{tasks_list}

## Available tools

You have access to the following tools which can help you determine if the dataset exists in the database:

- find_dataset
- web_search

## CRITICAL Requirements

1. **Prevent Duplicates**: Thoroughly search before concluding a dataset is not found. Duplicates cause data quality issues. Some datasets have multiple versions, e.g. there's SQuAD v1.1 and v2.
2. **Avoid False Positives**: Ensure the found dataset truly matches the mentioned one.
3. **Match Dataset Splits**: Some datasets have multiple splits and are considered different IDs in the database (e.g. there's CityScapes (validation) and CityScapes (test)). Ensure that the found dataset matches the same split as the mentioned dataset.
A dataset with split "test" is NOT the same as one with split "val" or without a split specified.

**IMPORTANT**: This list is ONLY for context. You MUST use the find_dataset tool to verify existence. Only set dataset_found=True if find_dataset returns "Found dataset: ID=X...".

**CRITICAL**: When a dataset is found, you MUST also call get_dataset_tasks_and_metrics(dataset_id=X) to retrieve:
- The task_ids associated with this dataset

This information is essential for correctly linking evaluation results to the right tasks and ensuring metrics are valid.

## Search Strategy

Use the find_dataset tool MULTIPLE TIMES with different strategies:

1. **Search by ArXiv ID** (most reliable if available):
   - find_dataset(arxiv_id="2103.00020")

2. **Search by Hugging Face URL** (if available):
   - Try full and partial URLs
   - find_dataset(hf_url="huggingface.co/datasets/...")

3. **Search by dataset name** (try variations):
   - Exact name as mentioned
   - Case variations (e.g., uppercase/lowercase)
   - With/without version numbers or suffixes
   - For hyphenated/underscored names: try exact name, then prefix only
   - Extract meaningful prefixes from compound names
   - Acronyms vs full names

4. **Combine criteria** for precision:
   - find_dataset(dataset_name="...", arxiv_id="...")

5. **Use web search** for disambiguation when available:
   - Verify if similar-named datasets are the same
   - Find official documentation for naming conventions

Only set dataset_found=False after exhausting ALL search strategies, listing the search strategies attempted in your reasoning.

## Output format

Use the following Pydantic model to format your response:

```python
class DatasetDetail(BaseModel):
    id: int  # ID of the dataset in the SQL database
    name: str  # Name of the dataset in the SQL database
    slug: str  # Slug of the dataset in the SQL database
    description: str  # Description of the dataset in the SQL database
    hf_url: str  # Hugging Face URL of the dataset in the SQL database
    paper_url: str  # Paper URL of the dataset in the SQL database
    task_ids: list[int] # List of task IDs associated with this dataset


class Response(BaseModel):
    reasoning: str  # Your reasoning regarding the search for the dataset, search strategies attempted and why you set dataset_found=True or False
    dataset_found: bool  # Whether the dataset was found in the SQL database
    dataset_detail: Optional[DatasetDetail] = (
        None  # The details of the found dataset, only complete this if dataset_found=True
    )
```

Return the response as a JSON string. Do not include any other text in your response.
"""


class Step2Input(BaseModel):
    """Input data for Step2."""

    arxiv_id: str
    dataset_details: list[dict]
    evaluation_results: list
    paper_details: str
    use_web_search: bool = True


class Step2SingleResult(BaseModel):
    """Result for a single dataset search."""

    dataset_input: dict
    found: bool
    reasoning: str
    dataset: Optional[DatasetDetail] = None


class Step2Output(BaseModel):
    """Output data for Step2 - now handles multiple datasets."""

    results: list[Step2SingleResult]
    paper_details: str  # Pass paper_details to next steps to avoid refetching


class Step2(AgentStep[Step2Input, Step2Output]):
    """Agent-based step for finding datasets in the database."""

    input_model = Step2Input
    output_model = Step2Output

    def __init__(self):
        super().__init__(
            name="Step2: Dataset Finder",
            description="Finds datasets in the database based on evaluation results",
            instructions=dataset_finder_prompt,
            tools=[find_dataset],
            agent_output_type=AgentOutputSchema(Response, strict_json_schema=False),
            model="gpt-5-mini",
            mcp_servers=["exa"],
        )

    async def _process_single_dataset(
        self,
        dataset_detail: dict,
        arxiv_id: str,
        evaluation_results: list,
        paper_details: str,
        formatted_instructions: str,
    ) -> Step2SingleResult:
        """
        Process a single dataset through the agent.

        Args:
            dataset_detail: Single dataset detail dict
            arxiv_id: ArXiv ID of the paper
            evaluation_results: List of evaluation results
            paper_details: Formatted paper details
            formatted_instructions: Pre-formatted instructions with tasks list

        Returns:
            Step2SingleResult with search outcome
        """
        dataset_name = dataset_detail.get("dataset_name", "Unknown")

        try:
            # Build prompt for this specific dataset
            prompt = f"""
## Paper details
{paper_details}

## Evaluation results

The evaluation results extracted by a colleague of yours are the following:
{json.dumps(evaluation_results, indent=2)}

## Dataset to find

Find the dataset details for the following dataset mentioned in the evaluation results:
{json.dumps(dataset_detail, indent=2)}
"""

            # Run the agent for this dataset
            agent_response = await self._run_agent(prompt, formatted_instructions)

            # Process the agent output
            if isinstance(agent_response, Response):
                if not agent_response.dataset_found:
                    print(f"Dataset '{dataset_name}' not found in database")
                    return Step2SingleResult(
                        dataset_input=dataset_detail,
                        found=False,
                        reasoning=agent_response.reasoning,
                        dataset=None,
                    )

                # Dataset was found - ensure task_ids are populated
                dataset_detail_result = agent_response.dataset_detail

                # If agent didn't populate task_ids, fetch them directly from database
                if not dataset_detail_result.task_ids:
                    from backend.database.connection import db_manager
                    from backend.services.dataset_service import DatasetService

                    session = db_manager.session_local()
                    try:
                        dataset_service = DatasetService(session)
                        task_ids = dataset_service.get_dataset_tasks(
                            dataset_detail_result.id
                        )
                        dataset_detail_result.task_ids = task_ids
                    finally:
                        session.close()

                print(
                    f"✓ Found dataset: {dataset_detail_result.name} (ID: {dataset_detail_result.id}, "
                    f"tasks: {dataset_detail_result.task_ids})"
                )
                return Step2SingleResult(
                    dataset_input=dataset_detail,
                    found=True,
                    reasoning=agent_response.reasoning,
                    dataset=dataset_detail_result,
                )
            else:
                raise ValueError(
                    f"Unexpected agent output type: {type(agent_response)}"
                )

        except Exception as e:
            print(f"Error processing dataset '{dataset_name}': {str(e)}")
            return Step2SingleResult(
                dataset_input=dataset_detail,
                found=False,
                reasoning=f"Error during search: {str(e)}",
                dataset=None,
            )

    async def run(self, inputs):
        """
        Override run to handle parallel processing of multiple datasets.
        """
        # Validate inputs if dict provided
        if isinstance(inputs, dict):
            try:
                inputs = Step2Input(**inputs)
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
            # Use string replacement instead of .format() to avoid issues with curly braces in tasks_list
            formatted_instructions = self.instructions.replace(
                "{tasks_list}", tasks_list
            )

            # Process all datasets in parallel
            tasks = [
                self._process_single_dataset(
                    dataset_detail=dataset_detail,
                    arxiv_id=inputs.arxiv_id,
                    evaluation_results=inputs.evaluation_results,
                    paper_details=inputs.paper_details,
                    formatted_instructions=formatted_instructions,
                )
                for dataset_detail in inputs.dataset_details
            ]

            results = await asyncio.gather(*tasks)

            # Return successful result with all findings
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=True,
                outputs=Step2Output(
                    results=list(results), paper_details=inputs.paper_details
                ),
                error_message=None,
            )

        except Exception as e:
            from extract_evaluation_results.step_base import StepResult

            return StepResult(
                success=False, outputs=None, error_message=f"Step 2 failed: {str(e)}"
            )
        finally:
            # Clean up MCP servers (in the same task context they were set up)
            # Suppress any cleanup errors as they're non-critical
            try:
                await self._cleanup_mcp_servers()
            except Exception as e:
                self.logger.debug(f"MCP server cleanup error (non-critical): {e}")

    async def build_agent_prompt(self, inputs: Step2Input) -> str:
        """
        Not used in the new parallel implementation.
        Kept for compatibility with base class signature.
        """
        raise NotImplementedError("Use _process_single_dataset instead")

    async def process_agent_output(
        self, agent_output: Any, inputs: Step2Input
    ) -> Step2Output:
        """
        Not used in the new parallel implementation.
        Kept for compatibility with base class signature.
        """
        raise NotImplementedError("Use _process_single_dataset instead")

    async def format_instructions(self, inputs: Step2Input) -> str:
        """
        Format instructions with paper-specific context.
        """
        # Format instructions with tasks list
        tasks_list = get_formatted_tasks_list()

        # Use string replacement instead of .format() to avoid issues with curly braces in tasks_list
        return self.instructions.replace("{tasks_list}", tasks_list)


def get_output_dir(arxiv_id: str) -> Path:
    """Get the output directory for a given arxiv_id.

    Returns: backend/outputs/evaluation_results/{arxiv_id}
    """
    output_dir = Path(__file__).parent.parent / "backend" / "outputs"
    eval_results_dir = output_dir / "evaluation_results" / arxiv_id
    eval_results_dir.mkdir(parents=True, exist_ok=True)
    return eval_results_dir


def read_step_1_output(arxiv_id: str) -> str:
    """Read the step_1 output JSON file from the standardized location.

    Reads from: backend/outputs/evaluation_results/{arxiv_id}/step_1.json

    Args:
        arxiv_id: The ArXiv ID of the paper
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_1.json"

    if not json_file.exists():
        raise FileNotFoundError(
            f"Could not find step_1 output file: {json_file}. "
            f"Run step_1.py first to generate the output."
        )

    return json_file.read_text()


def write_step_2_output(arxiv_id: str, results: list[dict]) -> None:
    """Write the step_2 output JSON file to the standardized location.

    Writes to: backend/outputs/evaluation_results/{arxiv_id}/step_2.json

    Args:
        arxiv_id: The ArXiv ID of the paper
        results: List of result dicts, each with 'dataset_input', 'found', 'reasoning', and optional 'dataset' keys
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_2.json"

    # Format the output as a list of results (consistent with parse.py format)
    output_data = [
        {
            "dataset": result.get("dataset_input", {}),
            "success": result.get("found", False),
            "result": result,
        }
        for result in results
    ]

    json_file.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
    print(f"✓ Step 2 output written to: {json_file}")


async def step_2(
    arxiv_id: str,
    dataset_details: list[dict],
    evaluation_results: list,
    paper_details: str,
    use_web_search: bool = True,
) -> list[dict]:
    """Process multiple dataset details to find them in the database (wrapper for Step2).

    Args:
        arxiv_id: The ArXiv ID of the paper containing the evaluation results
        dataset_details: List of dictionaries, each containing dataset_name, paper_title, paper_arxiv_id
        evaluation_results: List of evaluation results from step_1
        paper_details: Formatted paper details (title, authors, abstract)
        use_web_search: Whether to use Exa AI MCP server for web search

    Returns:
        List of dictionaries, each with 'dataset_input', 'found' bool, 'reasoning', and optional 'dataset' dict
    """
    agent = Step2()
    input_data = Step2Input(
        arxiv_id=arxiv_id,
        dataset_details=dataset_details,
        evaluation_results=evaluation_results,
        paper_details=paper_details,
        use_web_search=use_web_search,
    )
    result = await agent.run(input_data)

    if not result.success:
        print(f"Step 2 failed: {result.error_message}")
        # Return error results for all datasets
        return [
            {
                "dataset_input": dataset_detail,
                "found": False,
                "reasoning": result.error_message,
            }
            for dataset_detail in dataset_details
        ]

    # result.outputs is now a Step2Output model with a list of Step2SingleResult
    # Convert to list of dicts for backward compatibility
    output_list = []
    for single_result in result.outputs.results:
        output_dict = {
            "dataset_input": single_result.dataset_input,
            "found": single_result.found,
            "reasoning": single_result.reasoning,
        }
        if single_result.dataset:
            output_dict["dataset"] = single_result.dataset.model_dump()
        output_list.append(output_dict)

    return output_list


async def main():
    parser = argparse.ArgumentParser(
        description="Find datasets in the database based on evaluation results extracted from a paper."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper that contains the evaluation results.",
        default="2406.09414",
    )
    args = parser.parse_args()

    arxiv_id = args.arxiv_id

    # Read step_1 output from standardized JSON location
    step_1_output = read_step_1_output(arxiv_id)
    step_1_data = json.loads(step_1_output)
    evaluation_results = step_1_data["evaluation_results"]
    dataset_details = step_1_data["dataset_details"]

    # Check if there are any datasets to process
    if not dataset_details:
        print("No dataset details found in step_1 output")
        # Write empty result to step_2.json
        write_step_2_output(arxiv_id, [])
        return []

    print(f"Processing {len(dataset_details)} datasets in parallel...")
    for idx, dataset in enumerate(dataset_details, 1):
        print(f"  {idx}. {dataset.get('dataset_name', 'Unknown')}")

    # Paper details
    paper_details = await get_paper_details(arxiv_id)

    # Check for EXA_API_KEY
    exa_api_key = os.getenv("EXA_API_KEY")
    use_web_search = bool(exa_api_key)
    if not exa_api_key:
        print(
            "Warning: EXA_API_KEY not found. Web search disabled. Set EXA_API_KEY in backend/keys.env to enable web search for disambiguation."
        )

    # Process all datasets in parallel
    results = await step_2(
        arxiv_id=arxiv_id,
        dataset_details=dataset_details,
        evaluation_results=evaluation_results,
        paper_details=paper_details,
        use_web_search=use_web_search,
    )

    # Write the results to step_2.json
    write_step_2_output(arxiv_id, results)

    return results


if __name__ == "__main__":
    results = asyncio.run(main())
    if results:
        print("\n" + "=" * 50)
        print("RESULTS SUMMARY:")
        print("=" * 50)
        found_count = sum(1 for r in results if r.get("found"))
        print(f"Found {found_count}/{len(results)} datasets in database\n")
        for idx, result in enumerate(results, 1):
            dataset_name = result.get("dataset_input", {}).get(
                "dataset_name", "Unknown"
            )
            status = "✓" if result.get("found") else "✗"
            print(f"{idx}. {status} {dataset_name}")
            if result.get("found") and result.get("dataset"):
                db_name = result["dataset"].get("name", "Unknown")
                db_id = result["dataset"].get("id", "N/A")
                print(f"   → Found as: {db_name} (ID: {db_id})")
        print("=" * 50)
        print("\nDetailed results:")
        print(json.dumps(results, indent=2))
    else:
        print("No results received")


# Workflow integration
class Step2WorkflowStep:
    """Workflow step wrapper for Step2."""

    name = "Step2WorkflowStep"

    def __init__(self):
        self.step = Step2()

    async def execute(self, state):
        """
        Execute Step2 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str
        - dataset_details: list[dict]
        - evaluation_results: list
        - paper_details: str (optional, will be generated if not present)
        - use_web_search: bool (optional, defaults to True)

        Writes to state.data:
        - step_2_results: list of search results
        """
        from extract_evaluation_results.step_base import StepResult

        # Get paper_details if not in state
        paper_details = state.data.get("paper_details")
        if not paper_details:
            paper_details = await get_paper_details(
                state.data.get("arxiv_id", state.arxiv_id)
            )

        # Build inputs from state.data
        inputs = {
            "arxiv_id": state.data.get("arxiv_id", state.arxiv_id),
            "dataset_details": state.data.get("dataset_details", []),
            "evaluation_results": state.data.get("evaluation_results", []),
            "paper_details": paper_details,
            "use_web_search": state.data.get("use_web_search", True),
        }

        # Execute the step
        result = await self.step.run(inputs)

        # Rename 'results' to 'step_2_results' for clarity and preserve paper_details
        if result.success and result.outputs:
            from extract_evaluation_results.step_base import StepResult

            output_dict = result.outputs.model_dump()
            # Rename the key
            if "results" in output_dict:
                output_dict["step_2_results"] = output_dict.pop("results")

            # Create new output model with renamed field and paper_details
            from pydantic import BaseModel

            class Step2RenamedOutput(BaseModel):
                step_2_results: list
                paper_details: str

            renamed_output = Step2RenamedOutput(
                step_2_results=output_dict["step_2_results"],
                paper_details=output_dict["paper_details"],
            )

            return StepResult(
                success=True, outputs=renamed_output, reasoning=result.reasoning
            )

        return result
