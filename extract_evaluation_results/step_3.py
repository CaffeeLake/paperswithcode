"""
This script defines an agent that can gather information about a dataset.

It uses the Exa AI MCP server and Hugging Face MCP server to search the web for information about the dataset.

To use the Hugging Face MCP server, you need to add your Hugging Face API token to backend/keys.env:
  HF_TOKEN=hf_your_token_here

You can generate a token at: https://huggingface.co/settings/tokens

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --dataset_name "COCO"
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --arxiv_id "2103.00020"
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --hf_url "huggingface.co/datasets/imagenet-1k"
```
"""

import argparse
import asyncio
import os
from typing import Optional

from pydantic import BaseModel

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from extract_evaluation_results.step_2 import get_search_parts


class DatasetInformation(BaseModel):
    description: str
    full_name: str
    hf_url: Optional[str] = None
    conference_url: Optional[str] = None
    arxiv_id: Optional[str] = None


dataset_information_prompt = """
You are a helpful assistant that gathers information about a dataset.
You will be given a dataset name and you will need to gather information about the dataset by searching the web and Hugging Face.

You need to find the following information about the dataset:
- A description of the dataset
- The full name of the dataset
- The Hugging Face URL of the dataset, if available
- The ArXiv ID of the paper that introduced the dataset, if available (e.g., "2103.00020")
- The conference URL of the dataset, if available (e.g., "https://openaccess.thecvf.com/CVPR2021/papers/Kolesnikov_Decoupled_Attention_Network_for_Vision-Language_Tasks_CVPR_2021_paper.pdf")

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
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper."
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        help="The name of the dataset to find the ID for.",
        default=None,
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper that introduced the dataset.",
        default=None,
    )
    parser.add_argument(
        "--hf_url", type=str, help="The Hugging Face URL of the dataset.", default=None
    )
    args = parser.parse_args()

    dataset_name = args.dataset_name
    arxiv_id = args.arxiv_id
    hf_url = args.hf_url

    async def main(dataset_name: str, arxiv_id: str, hf_url: str):
        # Get EXA_API_KEY from environment
        exa_api_key = os.getenv("EXA_API_KEY")
        if not exa_api_key:
            print(
                "Warning: EXA_API_KEY not found in environment. Make sure to run with --env-file backend/keys.env"
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
                print("Successfully connected to Exa AI MCP server")
            except (Exception, asyncio.TimeoutError) as e:
                print(f"Warning: Could not connect to Exa AI MCP server: {e}")
                print("Cannot proceed without Exa AI server.")
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
                    print(
                        "Successfully connected to Hugging Face MCP server (using API token)"
                    )
                except (Exception, asyncio.TimeoutError) as e:
                    print(f"Warning: Could not connect to Hugging Face MCP server: {e}")
                    print("Continuing with Exa AI server only...")
                    # Ensure any partial initialization is cleaned up
                    try:
                        # If the server object was partially created, try to clean it up
                        if hasattr(hf_server, "_process") and hf_server._process:
                            hf_server._process.terminate()
                    except Exception:
                        pass
            else:
                print(
                    "Info: HF_TOKEN/HUGGINGFACE_API_KEY not found. Skipping Hugging Face MCP server."
                )
                print(
                    "To enable it, add HF_TOKEN to backend/keys.env with your Hugging Face API token (starts with hf_)"
                )

            dataset_information_agent = Agent(
                name="Dataset Information Gatherer",
                instructions=dataset_information_prompt,
                mcp_servers=entered_servers,
                output_type=DatasetInformation,
            )
            search_parts = await get_search_parts(dataset_name, arxiv_id, hf_url)
            result = await Runner.run(
                dataset_information_agent,
                f"Gather information about the following dataset: {search_parts}",
            )
            return result.final_output

    result = asyncio.run(main(dataset_name, arxiv_id, hf_url))
    print("Result: ", result)
