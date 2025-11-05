"""
This script finds datasets in the database based on evaluation results extracted from a paper.

It reads the output from step_1 (which extracts evaluation results and dataset details from a paper)
and uses an AI agent to search for each dataset mentioned in the database. The agent uses multiple
search strategies including searching by dataset name, ArXiv ID of the introducing paper, and
Hugging Face URL. It can also use web search for disambiguation when needed.

You can run it like so:

```bash
# Process a paper (reads step_1 output JSON file from standardized location)
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --arxiv_id "2406.09414"
```

The script will:
1. Read the step_1 output JSON file from backend/outputs/evaluation_results/{arxiv_id}/step_1.json
2. Process the first dataset mentioned in the step_1 output
3. Use an AI agent to search for the dataset in the database using multiple strategies
4. Return the dataset information if found, or "Dataset not found" if not found
5. Pretty print the JSON result
"""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from backend.database.connection import db_manager
from backend.utils.logging_utils import async_export_txt


from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from extract_evaluation_results.utils import (
    get_paper_details,
    get_formatted_tasks_list,
    find_dataset,
)


class DatasetDetail(BaseModel):
    dataset_name: str
    dataset_info: str  # What you know about this dataset - do not make up information, only use the information provided in the paper
    paper_title: Optional[str] = (
        None  # The title of the paper that introduces the dataset (cited in the paper)
    )
    paper_arxiv_id: Optional[str] = (
        None  # The ArXiv ID of the paper that introduces the dataset (cited in the paper)
    )


class Step2Response(BaseModel):
    reasoning: str  # Your reasoning regarding the search for the dataset
    dataset_found: bool  # Whether the dataset was found in the database
    dataset_detail: Optional[DatasetDetail] = (
        None  # The details of the dataset mentioned in the evaluation results
    )


dataset_finder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in managing datasets used for benchmarking machine learning models in a SQL database.
A colleague of yours has extracted evaluation results from a paper.
Your responsibility includes finding whether the dataset mentioned in the evaluation results is already present
in the database or not. In case the dataset is not yet present, simply return "Dataset not found".

## Context: Available Tasks and Datasets

Below is a list of tasks currently in the database along with their associated datasets. This provides context about the current information landscape of the PapersWithCode app:

{tasks_list}

**IMPORTANT**: This tasks list is ONLY for context and hints. You CANNOT determine if a dataset exists just by seeing it in this list. You MUST use the find_dataset tool to actually retrieve the dataset from the database. Only set dataset_found=True if the find_dataset tool returns "Found dataset: ID=X...".

## CRITICAL: Preventing Duplicate Datasets

It is ESSENTIAL that you thoroughly search for existing datasets before concluding that a dataset is not found.
Duplicate datasets in the database cause data quality issues and must be avoided.
On the other hand, false positives should also be avoided, try to figure out whether the mentioned dataset is
the same dataset as one in the database.

## Search Strategy

You MUST use the find_dataset tool MULTIPLE TIMES with different search strategies to thoroughly check for existing datasets.

**DO NOT just reason about datasets from the context list above - you MUST actually call the find_dataset tool!**

1. **First, search by ArXiv ID** (if available): This is the most reliable method. If the dataset details mention an ArXiv ID of the introducing paper, use it:
   - Call find_dataset with arxiv_id parameter
   - Example: find_dataset(arxiv_id="2103.00020")

2. **Second, search by Hugging Face URL** (if available): If the dataset details mention a Hugging Face URL:
   - Call find_dataset with hf_url parameter
   - Try both full URL and partial URL (e.g., "huggingface.co/datasets/imagenet-1k")
   - Example: find_dataset(hf_url="huggingface.co/datasets/imagenet-1k")

3. **Third, search by dataset name** (try multiple variations):
   - Call find_dataset with dataset_name parameter
   - Try the exact name as mentioned
   - Try common variations (e.g., "COCO" vs "Coco" vs "coco")
   - Try abbreviations (e.g., "ImageNet" vs "ILSVRC")
   - Try with and without version numbers or suffixes
   - **CRITICAL for hyphenated names**: If the dataset name contains hyphens or underscores (e.g., "NYU-D", "NYU_v2"):
     * Try the exact name first: "NYU-D"
     * Try just the prefix: "NYU" (datasets are often stored with shortened names)
     * Try common version variants: "NYU-D" → also try "NYUv2", "NYU-Depth", "NYUD"
     * Example: For "NYU-D", you must try: find_dataset("NYU-D"), then find_dataset("NYU"), then find_dataset("NYUv2")
   - Extract meaningful prefixes from compound names (e.g., "NYU-D" → try "NYU", "CIFAR-10" → try "CIFAR")
   - Example: find_dataset(dataset_name="COCO")

4. **Combine search criteria** when you have multiple pieces of information:
   - Call find_dataset with multiple parameters for more precise results
   - Example: find_dataset(dataset_name="COCO", arxiv_id="1405.0312")

5. **If initial searches fail, try alternative name variations**:
   - Remove version suffixes (e.g., "COCO-2017" → "COCO")
   - Extract and search for prefixes/substrings (e.g., "NYU-Depth" → "NYU", "NYU-Depth" → "Depth")
   - Try acronyms vs full names
   - Try common misspellings or alternative spellings

6. **Use web search for disambiguation** (if available):
   - If you find datasets with similar names but are unsure if they're the same, use web search to verify
   - Search for information comparing the mentioned dataset name with candidate datasets found in the database
   - Use web search to find official documentation, papers, or resources that clarify dataset naming conventions
   - Example: If searching for "Dataset-A" and finding "Dataset-B" in database, search web for "Dataset-A vs Dataset-B" or "Dataset-A Dataset-B same"
   - This helps avoid both false positives (linking to wrong dataset) and false negatives (missing an existing dataset)

Only return "Dataset not found" after you have exhausted ALL possible search strategies and variations, including web search disambiguation when needed.

## Reporting Your Findings

When you find a dataset using the find_dataset tool:
1. The tool will return something like: "Found dataset: ID=74, Name=CityScapes, Slug=cityscapes..."
2. You MUST include this dataset ID in your reasoning field, using the format "ID=X" or "ID: X"
3. Set dataset_found=True
4. Example reasoning: "I searched for 'Cityscapes' and found a match in the database: ID=74, Name=CityScapes"

When you don't find a dataset after exhausting all search strategies:
1. Set dataset_found=False
2. Explain what searches you tried in your reasoning
3. Example reasoning: "I searched for 'SomeDataset' using variations X, Y, Z but found no matches in the database."

## Output Format

```python
class DatasetDetail(BaseModel):
    dataset_name: str
    dataset_info: str # What you know about this dataset - do not make up information, only use the information provided in the paper
    paper_title: Optional[str] = None # The title of the paper that introduces the dataset (cited in the paper)
    paper_arxiv_id: Optional[str] = None # The ArXiv ID of the paper that introduces the dataset (cited in the paper)


class Step2Response(BaseModel):
    reasoning: str # Your reasoning regarding the search for the dataset
    dataset_found: bool # Whether the dataset was found in the database
    dataset_detail: Optional[DatasetDetail] = None # The details of the dataset mentioned in the evaluation results
```

**IMPORTANT**: Extract the dataset information from the find_dataset tool results. When the tool returns "Found dataset: ID=X, Name=Y, Slug=Z...", parse that information and return it as JSON. Do NOT return code blocks or model definitions - only return the JSON data or "Dataset not found".
"""


async def create_dataset_finder_agent(mcp_servers=None) -> Agent:
    """Create the dataset finder agent with optional MCP servers for web search."""
    # Get tasks list for context
    tasks_list = get_formatted_tasks_list()
    # Build prompt with tasks context
    prompt_with_context = dataset_finder_prompt.format(tasks_list=tasks_list)

    return Agent(
        name="Dataset Finder",
        instructions=prompt_with_context,
        tools=[find_dataset],
        mcp_servers=mcp_servers or [],
        output_type=Step2Response,
    )


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


def write_step_2_output(arxiv_id: str, dataset_detail: dict, result: dict) -> None:
    """Write the step_2 output JSON file to the standardized location.

    Writes to: backend/outputs/evaluation_results/{arxiv_id}/step_2.json

    Args:
        arxiv_id: The ArXiv ID of the paper
        dataset_detail: The dataset detail that was processed
        result: The result dict from step_2 with 'found' and optional 'dataset' keys
    """
    eval_results_dir = get_output_dir(arxiv_id)
    json_file = eval_results_dir / "step_2.json"

    # Format the output as a list with one result (consistent with parse.py format)
    output_data = [
        {
            "dataset": dataset_detail,
            "success": result.get("found", False),
            "result": result,
        }
    ]

    json_file.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
    print(f"✓ Step 2 output written to: {json_file}")


def load_dataset_from_db(dataset_id: int) -> Optional[dict]:
    """Load dataset details from the database by ID.

    Args:
        dataset_id: The database ID of the dataset

    Returns:
        Dictionary with dataset info if found, None otherwise
    """
    session = db_manager.session_local()
    try:
        from backend.models.database import Dataset as DBDataset

        dataset = session.query(DBDataset).filter(DBDataset.id == dataset_id).first()
        if not dataset:
            return None

        return {
            "id": dataset.id,
            "name": dataset.name,
            "slug": dataset.slug,
            "full_name": dataset.full_name,
            "description": dataset.description,
            "hf_url": dataset.hf_url,
            "paper_url": dataset.paper_url,
        }
    finally:
        session.close()


def extract_dataset_id(result: str | dict) -> Optional[int]:
    """Extract dataset ID from step_2 result.

    Args:
        result: Either a result dict or a string representation of the result

    Returns:
        Dataset ID if found, None otherwise
    """
    # If result is a dict, check for 'found' and 'dataset' keys
    if isinstance(result, dict):
        if result.get("found") and result.get("dataset"):
            return result["dataset"].get("id")
        return None

    # If result is a string, try to extract ID using regex
    result_str = str(result)

    # Try to extract ID from patterns like "ID=123" or "ID: 123"
    id_match = re.search(r"ID[=:]?\s*(\d+)", result_str, re.IGNORECASE)
    if id_match:
        return int(id_match.group(1))

    # Also try to parse as JSON if it looks like a dict string
    if "{" in result_str:
        try:
            parsed = json.loads(result_str)
            if isinstance(parsed, dict):
                return extract_dataset_id(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def parse_dataset_info(result: str | dict) -> Optional[dict]:
    """Parse dataset information from step_2 result.

    Args:
        result: Either a result dict or a string representation of the result

    Returns:
        Dataset info dict if found and valid, None otherwise
    """
    # If result is a dict, check if dataset was found
    if isinstance(result, dict):
        if not result.get("found"):
            return None

        dataset_info = result.get("dataset")
        if dataset_info and dataset_info.get("id"):
            return dataset_info
        return None

    # If result is a string, try to extract dataset info
    result_str = str(result)

    # Check for explicit "not found" messages
    if "Dataset not found" in result_str or "not found" in result_str.lower():
        return None

    # Try to extract ID first
    dataset_id = extract_dataset_id(result_str)
    if not dataset_id:
        return None

    # If we have an ID, try to load from database
    return load_dataset_from_db(dataset_id)


async def step_2(
    arxiv_id: str,
    dataset_detail: dict,
    evaluation_results: list,
    paper_details: str,
    use_web_search: bool = True,
) -> dict:
    """Process a single dataset detail to find it in the database.

    Args:
        arxiv_id: The ArXiv ID of the paper containing the evaluation results
        dataset_detail: A dictionary containing dataset_name, paper_title, paper_arxiv_id
        evaluation_results: List of evaluation results from step_1
        paper_details: Formatted paper details (title, authors, abstract)
        use_web_search: Whether to use Exa AI MCP server for web search

    Returns:
        Dictionary with 'found' bool and 'dataset' dict (if found)
    """
    dataset_name = dataset_detail.get("dataset_name", "Unknown")
    print(f"Processing dataset: {dataset_name}")

    prompt = f"""
## Paper details
{paper_details}

## Evaluation results

The extracted evaluation results are the following:
{json.dumps(evaluation_results, indent=2)}

## Dataset to find

Find the dataset details for the following dataset mentioned in the evaluation results:
{json.dumps(dataset_detail, indent=2)}
"""

    # Helper function to run agent and process output
    async def run_agent_and_process(mcp_servers):
        dataset_finder_agent = await create_dataset_finder_agent(
            mcp_servers=mcp_servers
        )
        result = await Runner.run(dataset_finder_agent, prompt)

        if not result or not hasattr(result, "final_output"):
            raise ValueError(f"Agent returned invalid result: {result}")

        final_output = result.final_output

        # Ensure we have a Step2Response object
        if not isinstance(final_output, Step2Response):
            raise ValueError(f"Expected Step2Response, got {type(final_output)}")

        # If dataset not found, return early
        if not final_output.dataset_found:
            print(f"Dataset '{dataset_name}' not found in database")
            return {"found": False, "reasoning": final_output.reasoning}

        # Extract dataset ID from reasoning (look for "ID=X" pattern)
        dataset_id = None
        id_match = re.search(r"ID[=:](\d+)", final_output.reasoning)
        if id_match:
            dataset_id = int(id_match.group(1))

        if not dataset_id:
            print("⚠️  WARNING: Agent claimed dataset was found but no ID in reasoning")
            return {"found": False, "reasoning": final_output.reasoning}

        # Load actual dataset from database
        db_dataset = load_dataset_from_db(dataset_id)
        if not db_dataset:
            print(
                f"⚠️  WARNING: Dataset ID {dataset_id} does not exist in database. Rejecting false positive."
            )
            return {"found": False, "reasoning": final_output.reasoning}

        print(f"✓ Found dataset: {db_dataset['name']} (ID: {dataset_id})")
        return {
            "found": True,
            "reasoning": final_output.reasoning,
            "dataset": db_dataset,
        }

    # Try with web search first if available
    exa_api_key = os.getenv("EXA_API_KEY")
    if use_web_search and exa_api_key:
        try:
            async with MCPServerStdio(
                name="Exa AI MCP Server",
                params={
                    "command": "npx",
                    "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"],
                    "env": {"EXA_API_KEY": exa_api_key},
                },
                client_session_timeout_seconds=10,
            ) as exa_server:
                async with MCPServerStdio(
                    name="Hugging Face MCP Server",
                    params={
                        "command": "npx",
                        "args": [
                            "-y",
                            "mcp-remote",
                            "https://huggingface.co/mcp?login",
                        ],
                    },
                    client_session_timeout_seconds=10,
                ) as hf_server:
                    return await run_agent_and_process([exa_server, hf_server])
        except Exception as e:
            print(f"Warning: Could not set up MCP servers: {e}")
            print("Continuing without web search...")

    # Run without web search
    return await run_agent_and_process([])


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

    # Focus on the first dataset mentioned
    if not dataset_details:
        print("No dataset details found in step_1 output")
        # Write empty result to step_2.json
        empty_result = {"found": False, "reasoning": "No dataset details found"}
        write_step_2_output(arxiv_id, {}, empty_result)
        return empty_result

    first_dataset = dataset_details[0]
    print(f"Checking first dataset: {first_dataset}")

    # Paper details
    paper_details = await get_paper_details(arxiv_id)

    await async_export_txt(
        filename=f"step_2_{arxiv_id}",
        value=f"Processing dataset: {json.dumps(first_dataset, indent=2)}",
    )

    # Check for EXA_API_KEY
    exa_api_key = os.getenv("EXA_API_KEY")
    use_web_search = bool(exa_api_key)
    if not exa_api_key:
        print(
            "Warning: EXA_API_KEY not found. Web search disabled. Set EXA_API_KEY in backend/keys.env to enable web search for disambiguation."
        )

    # Process the dataset
    result = await step_2(
        arxiv_id=arxiv_id,
        dataset_detail=first_dataset,
        evaluation_results=evaluation_results,
        paper_details=paper_details,
        use_web_search=use_web_search,
    )

    # Write the result to step_2.json
    write_step_2_output(arxiv_id, first_dataset, result)

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\n" + "=" * 50)
        print("RESULT:")
        print("=" * 50)
        print(json.dumps(result, indent=2))
    else:
        print("No result received")
