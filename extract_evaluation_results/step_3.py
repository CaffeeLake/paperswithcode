"""
This script defines an agent that can gather information about a dataset.

It uses the Exa AI MCP server and Hugging Face MCP server to search the web/HF for information about the dataset.

To use the Hugging Face MCP server, you need to add your Hugging Face API token to backend/keys.env:
  HF_TOKEN=hf_your_token_here

You can generate a token at: https://huggingface.co/settings/tokens

This script is typically used after step_2.py fails to find a dataset in the database.
It takes the dataset_details extracted from step_1.py and gathers additional information
about the dataset from the web and Hugging Face.

You can run it like so:

```bash
# Using dataset_details JSON (recommended)
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
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from extract_evaluation_results.step_2 import get_search_parts

logger = logging.getLogger(__name__)


class DatasetInformation(BaseModel):
    description: str
    full_name: str
    hf_url: Optional[str] = None
    conference_url: Optional[str] = None
    arxiv_id: Optional[str] = None


dataset_information_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You will be given information about a dataset that was mentioned in the evaluation results of a research paper but
could not be found in the SQL database of Hugging Face's Leaderboards project.
Your task is to gather comprehensive information about this dataset by searching the web and Hugging Face, so that
it can be added to the SQL database.

You will be provided with:
- The dataset name (as mentioned in the paper)
- Any information about the dataset that was extracted from the paper
- Potentially the ArXiv ID of the paper that introduced the dataset
- Potentially the title of the paper that introduced the dataset

You need to find the following information about the dataset:
- A comprehensive description of the dataset
- The full name of the dataset
- The Hugging Face URL of the dataset, if available
- The ArXiv ID of the paper that introduced the dataset, if available (e.g., "2103.00020")
- The conference URL of the dataset, if available (e.g., "https://openaccess.thecvf.com/CVPR2021/papers/Kolesnikov_Decoupled_Attention_Network_for_Vision-Language_Tasks_CVPR_2021_paper.pdf")

Use the provided dataset information as context, but verify and expand on it using web search and Hugging Face.

## Output format
```python
from pydantic import BaseModel

class DatasetInformation(BaseModel):
    description: str
    full_name: str
    hf_url: Optional[str] = None
    conference_url: Optional[str] = None
    arxiv_id: Optional[str] = None
```

Return the information as a JSON string.
Do not make up information, only use the information provided in the web search and Hugging Face.
Make sure to find as much information as possible about the dataset.
"""


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gather information about a dataset from the web and Hugging Face."
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
    # Backward compatibility: keep individual parameters
    parser.add_argument(
        "--dataset_name",
        type=str,
        help="[Backward compatibility] The name of the dataset.",
        default=None,
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="[Backward compatibility] The ArXiv ID of the paper that introduced the dataset.",
        default=None,
    )
    parser.add_argument(
        "--hf_url",
        type=str,
        help="[Backward compatibility] The Hugging Face URL of the dataset.",
        default=None,
    )
    args = parser.parse_args()

    # Parse dataset_details if provided
    dataset_detail = None
    if args.dataset_details:
        dataset_detail = parse_dataset_details(args.dataset_details)
    elif args.dataset_details_file:
        dataset_detail = parse_dataset_details(args.dataset_details_file)

    # Extract values from dataset_detail or use backward compatibility parameters
    if dataset_detail:
        dataset_name = dataset_detail.get("dataset_name")
        arxiv_id = dataset_detail.get("paper_arxiv_id")
        hf_url = None  # Not typically in dataset_detail
        dataset_info = dataset_detail.get("dataset_info", "")
        paper_title = dataset_detail.get("paper_title")
    else:
        # Backward compatibility mode
        dataset_name = args.dataset_name
        arxiv_id = args.arxiv_id
        hf_url = args.hf_url
        dataset_info = None
        paper_title = None

    if not dataset_name and not arxiv_id and not hf_url:
        parser.error(
            "Must provide either --dataset_details/--dataset_details_file or at least one of --dataset_name, --arxiv_id, or --hf_url"
        )

    async def main(
        dataset_name: Optional[str],
        arxiv_id: Optional[str],
        hf_url: Optional[str],
        dataset_info: Optional[str] = None,
        paper_title: Optional[str] = None,
    ):
        return await step_3(
            dataset_name=dataset_name,
            arxiv_id=arxiv_id,
            hf_url=hf_url,
            dataset_info=dataset_info,
            paper_title=paper_title,
        )


async def step_3(
    dataset_name: Optional[str],
    arxiv_id: Optional[str],
    hf_url: Optional[str],
    dataset_info: Optional[str] = None,
    paper_title: Optional[str] = None,
) -> Optional[DatasetInformation]:
    """Gather information about a dataset from the web and Hugging Face."""
    # Get EXA_API_KEY from environment
    exa_api_key = os.getenv("EXA_API_KEY")
    if not exa_api_key:
        logger.warning(
            "EXA_API_KEY not found in environment. Make sure to run with --env-file backend/keys.env"
        )
        return None

    # Set up MCP servers
    # Use contextlib.AsyncExitStack to manage multiple context managers
    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        entered_servers = []

        # Try to enter Exa server context (required)
        exa_server = MCPServerStdio(
            name="Exa AI MCP Server",
            params={
                "command": "npx",
                "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"],
                "env": {
                    "EXA_API_KEY": exa_api_key,
                },
            },
            client_session_timeout_seconds=30,
        )
        try:
            entered_exa = await asyncio.wait_for(
                stack.enter_async_context(exa_server), timeout=35.0
            )
            entered_servers.append(entered_exa)
            logger.info("Successfully connected to Exa AI MCP server")
        except (Exception, asyncio.TimeoutError) as e:
            logger.warning(f"Could not connect to Exa AI MCP server: {e}")
            logger.warning("Cannot proceed without Exa AI server.")
            return None

        # Try to enter Hugging Face server context (optional)
        # Use API token if available, otherwise skip (requires OAuth which doesn't work in headless mode)
        hf_token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGINGFACE_TOKEN")
        )

        if hf_token:
            # Use token-based authentication
            hf_server = MCPServerStdio(
                name="Hugging Face MCP Server",
                params={
                    "command": "npx",
                    "args": [
                        "-y",
                        "mcp-remote",
                        "https://huggingface.co/mcp",
                        "--header",
                        f"Authorization: Bearer {hf_token}",
                    ],
                },
                client_session_timeout_seconds=30,
            )
            try:
                entered_hf = await asyncio.wait_for(
                    stack.enter_async_context(hf_server), timeout=35.0
                )
                entered_servers.append(entered_hf)
                logger.info(
                    "Successfully connected to Hugging Face MCP server (using API token)"
                )
            except (Exception, asyncio.TimeoutError) as e:
                logger.warning(f"Could not connect to Hugging Face MCP server: {e}")
                logger.info("Continuing with Exa AI server only...")
                # Ensure any partial initialization is cleaned up
                try:
                    # If the server object was partially created, try to clean it up
                    if hasattr(hf_server, "_process") and hf_server._process:
                        hf_server._process.terminate()
                except Exception:
                    pass
        else:
            logger.info(
                "HF_TOKEN/HUGGINGFACE_API_KEY not found. Skipping Hugging Face MCP server."
            )
            logger.info(
                "To enable it, add HF_TOKEN to backend/keys.env with your Hugging Face API token (starts with hf_)"
            )

        dataset_information_agent = Agent(
            name="Dataset Information Gatherer",
            instructions=dataset_information_prompt,
            mcp_servers=entered_servers,
            output_type=DatasetInformation,
        )
        search_parts = await get_search_parts(
            dataset_name or "", arxiv_id or "", hf_url or ""
        )

        # Build the prompt with dataset information
        prompt_parts = [
            f"Gather information about the following dataset: {search_parts}"
        ]

        if dataset_info:
            prompt_parts.append("\n## Information extracted from the paper:")
            prompt_parts.append(f"{dataset_info}")

        if paper_title:
            prompt_parts.append("\n## Paper that introduced the dataset:")
            prompt_parts.append(f"Title: {paper_title}")

        prompt = "\n".join(prompt_parts)

        result = await Runner.run(
            dataset_information_agent,
            prompt,
        )
        return result.final_output

    result = asyncio.run(
        main(
            dataset_name=dataset_name,
            arxiv_id=arxiv_id,
            hf_url=hf_url,
            dataset_info=dataset_info,
            paper_title=paper_title,
        )
    )
    print("Result: ", result)
