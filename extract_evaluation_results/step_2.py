"""
This script defines an agent that can find dataset details in the database.

You can run it like so:

```bash
# Find a dataset by name
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --dataset_name "COCO"

# Find a dataset by ArXiv ID (of the introducing paper)
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --arxiv_id "2103.00020"

# Find a dataset by Hugging Face URL
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --hf_url "huggingface.co/datasets/imagenet-1k"
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from backend.database.connection import db_manager
from backend.utils.logging_utils import async_export_txt
from backend.utils.paper_utils import get_title, get_authors, get_abstract

from sqlalchemy.orm import Session

from agents import Agent, function_tool, Runner
from agents.mcp import MCPServerStdio

dataset_finder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in managing datasets used for benchmarking machine learning models in a SQL database.
A colleague of yours has extracted evaluation results from a paper.
Your responsibility includes finding whether the dataset mentioned in the evaluation results is already present
in the database or not. In case the dataset is not yet present, simply return "Dataset not found".

## CRITICAL: Preventing Duplicate Datasets

It is ESSENTIAL that you thoroughly search for existing datasets before concluding that a dataset is not found.
Duplicate datasets in the database cause data quality issues and must be avoided.
On the other hand, false positives should also be avoided, try to figure out whether the mentioned dataset is
the same dataset as one in the database.

## Search Strategy

You MUST use the find_dataset tool MULTIPLE TIMES with different search strategies to thoroughly check for existing datasets:

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
   - **IMPORTANT**: If the dataset name contains hyphens or underscores (e.g., "NYU-D", "NYU_v2"), also try searching for just the prefix part (e.g., search for "NYU" when given "NYU-D")
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

## Output Format

If the dataset is found in the database, return a JSON string with the dataset information:
```json
{
  "found": true,
  "id": 72,
  "name": "ImageNet-1k",
  "slug": "imagenet-1k",
  "description": "Dataset description...",
  "hf_url": "https://huggingface.co/datasets/...",
  "paper_url": "https://arxiv.org/abs/..."
}
```

If the dataset is NOT found, return simply:
```
Dataset not found
```

**IMPORTANT**: Extract the dataset information from the find_dataset tool results. When the tool returns "Found dataset: ID=X, Name=Y, Slug=Z...", parse that information and return it as JSON. Do NOT return code blocks or model definitions - only return the JSON data or "Dataset not found".
"""


@function_tool
async def find_dataset(
    dataset_name: str | None = None,
    arxiv_id: str | None = None,
    hf_url: str | None = None,
) -> str:
    """Find a dataset in the database by name, ArXiv ID, or Hugging Face URL.

    This tool supports case-insensitive partial matching. You should call this tool multiple times
    with different search strategies to thoroughly check for existing datasets before concluding
    that a dataset is not found.

    Args:
        dataset_name: The name of the dataset to find (case-insensitive partial matching).
                     Searches in name, full_name, and description fields.
        arxiv_id: The ArXiv ID of the paper that introduced the dataset (e.g., "2103.00020").
                 This searches for datasets where the introducing paper has this ArXiv ID.
                 Version numbers are automatically ignored (e.g., "2103.00020v2" matches "2103.00020").
        hf_url: The Hugging Face URL of the dataset (partial matching supported).
               Can be full URL or partial (e.g., "huggingface.co/datasets/imagenet-1k").

    Returns:
        A JSON string with dataset information if found, or "Dataset not found" if not found.

    Important:
        - At least one of dataset_name, arxiv_id, or hf_url must be provided.
        - If multiple parameters are provided, they are combined with AND logic.
        - Call this tool multiple times with different search strategies to ensure thorough searching.
        - Try searching by ArXiv ID first (most reliable), then HF URL, then dataset name with variations.
    """
    # Log tool call for debugging
    search_params = []
    if dataset_name:
        search_params.append(f"dataset_name='{dataset_name}'")
    if arxiv_id:
        search_params.append(f"arxiv_id='{arxiv_id}'")
    if hf_url:
        search_params.append(f"hf_url='{hf_url}'")
    print(f"[TOOL CALL] find_dataset({', '.join(search_params)})")

    if not dataset_name and not arxiv_id and not hf_url:
        return "Error: At least one search parameter (dataset_name, arxiv_id, or hf_url) must be provided"

    session: Session = db_manager.session_local()

    from backend.models.database import Dataset as DBDataset, Paper as DBPaper
    from sqlalchemy import and_, or_, select

    try:
        # Build query with filters
        query = session.query(DBDataset)
        filters = []

        # Search by ArXiv ID (of the introducing paper)
        if arxiv_id:
            # Normalize arxiv_id (remove version if present)
            arxiv_base = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

            # Find papers with matching ArXiv ID
            paper_subquery = (
                select(DBPaper.id)
                .filter(DBPaper.arxiv_id.like(f"{arxiv_base}%"))
                .scalar_subquery()
            )

            filters.append(DBDataset.introducing_paper_id.in_(paper_subquery))

        # Search by Hugging Face URL
        if hf_url:
            # Support partial matching for HF URLs
            filters.append(DBDataset.hf_url.ilike(f"%{hf_url}%"))

        # Search by dataset name
        if dataset_name:
            # Try direct search first
            name_filters = or_(
                DBDataset.name.ilike(f"%{dataset_name}%"),
                DBDataset.full_name.ilike(f"%{dataset_name}%"),
                DBDataset.description.ilike(f"%{dataset_name}%"),
            )
            filters.append(name_filters)

        # Apply all filters
        if filters:
            query = query.filter(and_(*filters))

        # Prioritize exact matches and base datasets (no parent)
        # First try exact name match (case-insensitive)
        if dataset_name:
            exact_match = query.filter(DBDataset.name.ilike(dataset_name)).first()
            if exact_match:
                db_dataset = exact_match
            else:
                # Try to prioritize base datasets (no parent_dataset_id) and shorter names
                # Order by: parent_dataset_id NULL first (base datasets), then by name alphabetically
                db_dataset = query.order_by(
                    DBDataset.parent_dataset_id.asc().nullsfirst(),
                    DBDataset.name.asc(),
                ).first()
        else:
            # Execute query without name priority
            db_dataset = query.first()

        if not db_dataset:
            session.close()
            result = "Dataset not found"
            print(f"[TOOL RESULT] {result}")
            return result

        # Format response with key information
        response = f"Found dataset: ID={db_dataset.id}, Name={db_dataset.name}, Slug={db_dataset.slug}"
        if db_dataset.full_name:
            response += f", Full Name={db_dataset.full_name}"
        if db_dataset.description:
            desc_preview = (
                db_dataset.description[:100] + "..."
                if len(db_dataset.description) > 100
                else db_dataset.description
            )
            response += f", Description={desc_preview}"
        if db_dataset.hf_url:
            response += f", HF URL={db_dataset.hf_url}"
        if db_dataset.paper_url:
            response += f", Paper URL={db_dataset.paper_url}"

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except Exception as e:
        session.close()
        error_msg = f"Error searching for dataset: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg


async def get_search_parts(dataset_name: str, arxiv_id: str, hf_url: str) -> str:
    search_parts = []

    if not dataset_name and not arxiv_id and not hf_url:
        raise ValueError(
            "At least one search parameter (dataset_name, arxiv_id, or hf_url) must be provided"
        )

    if dataset_name:
        search_parts.append(f"Dataset name: '{dataset_name}'")
    if arxiv_id:
        search_parts.append(f"ArXiv ID: '{arxiv_id}'")
    if hf_url:
        search_parts.append(f"HF URL: '{hf_url}'")
    return " and ".join(search_parts)


async def create_dataset_finder_agent(mcp_servers=None) -> Agent:
    """Create the dataset finder agent with optional MCP servers for web search."""
    return Agent(
        name="Dataset Finder",
        instructions=dataset_finder_prompt,
        tools=[find_dataset],
        mcp_servers=mcp_servers or [],
    )


async def get_paper_details(arxiv_id: str) -> str:
    paper_title = await get_title(arxiv_id)
    paper_authors = await get_authors(arxiv_id)
    paper_abstract = await get_abstract(arxiv_id)

    return f"""
### Title:
{paper_title}
### Authors:
{paper_authors}
### ArXiv ID
{arxiv_id}
### Abstract
{paper_abstract}
"""


def read_step_1_output(filename: str) -> str:
    """Read the step_1 output file."""
    # Try backend/outputs first, then extract_evaluation_results
    output_dir = Path(__file__).parent.parent / "backend" / "outputs"
    file_path = output_dir / filename
    if not file_path.exists():
        # Fallback to extract_evaluation_results directory
        file_path = Path(__file__).parent / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find step_1 output file: {filename}")
    return file_path.read_text()


async def step_2(
    arxiv_id: str,
    dataset_detail: dict,
    evaluation_results: list,
    paper_details: str,
    use_web_search: bool = True,
) -> str:
    """Process a single dataset detail to find it in the database.

    Args:
        arxiv_id: The ArXiv ID of the paper containing the evaluation results
        dataset_detail: A dictionary containing dataset_name, paper_title, paper_arxiv_id
        evaluation_results: List of evaluation results from step_1
        paper_details: Formatted paper details (title, authors, abstract)
        use_web_search: Whether to use Exa AI MCP server for web search

    Returns:
        The result from the dataset finder agent
    """
    print(f"Processing dataset: {dataset_detail.get('dataset_name', 'Unknown')}")

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

    # Set up web search via Exa AI MCP server and Hugging Face MCP server (optional)
    exa_api_key = os.getenv("EXA_API_KEY")
    if use_web_search and exa_api_key:
        try:
            # Set up Exa AI MCP server for web search
            async with MCPServerStdio(
                name="Exa AI MCP Server",
                params={
                    "command": "npx",
                    "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"],
                    "env": {
                        "EXA_API_KEY": exa_api_key,
                    },
                },
                client_session_timeout_seconds=10,
            ) as exa_server:
                # Set up Hugging Face MCP server
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
                    dataset_finder_agent = await create_dataset_finder_agent(
                        mcp_servers=[exa_server, hf_server]
                    )
                    # Run the dataset finder agent
                    result = await Runner.run(dataset_finder_agent, prompt)
                    return result.final_output
        except Exception as e:
            print(f"Warning: Could not set up MCP servers for web search: {e}")
            print("Continuing without web search capability...")

    # Run without web search
    dataset_finder_agent = await create_dataset_finder_agent(mcp_servers=[])
    result = await Runner.run(dataset_finder_agent, prompt)
    return result.final_output


async def main():
    parser = argparse.ArgumentParser(
        description="Find or add a dataset in the database using a set of AI agents."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper that contains the evaluation results.",
        default="2406.09414",
    )
    parser.add_argument(
        "--step_1_output_file",
        type=str,
        help="The step_1 output filename to read.",
        default="step_1_2406.09414.txt",
    )
    args = parser.parse_args()

    arxiv_id = args.arxiv_id

    # Read step_1 output
    step_1_output = read_step_1_output(args.step_1_output_file)
    step_1_data = json.loads(step_1_output)
    evaluation_results = step_1_data["evaluation_results"]
    dataset_details = step_1_data["dataset_details"]

    # Focus on the first dataset mentioned
    if not dataset_details:
        print("No dataset details found in step_1 output")
        return "No dataset details found"

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
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    print("Result: ", result)
