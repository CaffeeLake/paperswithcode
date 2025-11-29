"""
This script defines an agent that uses the `parse.py` script using the bash tool to execute it.
The agent is used to execute the script, check whether the script succeeded, whether evaluation results
were properly added to the database and no duplicates were added.

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/agent.py --arxiv_id 2201.03545
```
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

from agents import Agent, LocalShellTool, Runner

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Response(BaseModel):
    """Response model for the agent output."""

    reasoning: str  # Reasoning regarding the execution and verification
    script_succeeded: bool  # Whether the parse.py script executed successfully
    evaluation_results_added: Optional[int] = None  # Number of evaluation results added
    duplicates_found: Optional[int] = None  # Number of duplicates found
    errors: Optional[list[str]] = None  # List of any errors encountered


instructions_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape
by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI), titled the PapersWithCode project.
This way, people can track progress of state-of-the-art models over time.

You are an agent capable of running the `parse.py` script which runs an agentic workflow to extract evaluation results from an AI research paper
released on ArXiv.

Your task is to:
1. Run the `parse.py` script with the provided ArXiv ID
2. Check whether the script succeeded by examining its output
3. Verify whether evaluation results were properly added to the database
4. Check for any duplicate datasets, metrics or evaluation results that were added and remove them if necessary

## Running the Script

The `parse.py` script is located in the `extract_evaluation_results/` directory.
You should run it using:
```bash
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id <ARXIV_ID>
```

The script will output a summary at the end showing:
- Step 1: Number of evaluation results and datasets extracted
- Step 2: Number of datasets found in the database
- Step 3: Number of datasets for which information was gathered
- Step 4: Number of datasets added to the database
- Step 5: Number of metrics mapped and unresolved
- Step 6: Number of evaluation results normalized
- Step 7: Number of evaluations added and skipped (duplicates)

## Checking for Success

The script succeeds if:
- The exit code is 0
- The summary shows "Success: True"
- Step 7 shows evaluations were added (or skipped if duplicates)

## Checking for Duplicates

Look at the Step 7 output in the summary:
- If it shows "X evaluations added, Y skipped (duplicates)", then Y duplicates were found and skipped
- This is expected behavior - the script should skip duplicates rather than add them

## Error Handling

If the script fails:
1. Check the error message in the output
2. You can try re-running with the `--resume` flag if the error suggests cached data might help
3. Report the error clearly in your response

## Output Format

You must return a JSON response matching this structure:
```json
{
  "reasoning": "Your detailed reasoning about what happened",
  "script_succeeded": true/false,
  "evaluation_results_added": number or null,
  "duplicates_found": number or null,
  "errors": ["error1", "error2"] or null
}
```

Return ONLY the JSON response, no other text.
"""


async def run_agent(arxiv_id: str) -> Response:
    """
    Run the agent to execute parse.py and verify results.

    Args:
        arxiv_id: The ArXiv ID of the paper to process

    Returns:
        Response model with execution results
    """
    # Get the project root directory (parent of extract_evaluation_results)
    project_root = Path(__file__).parent.parent.absolute()

    # Create the agent with LocalShellTool
    agent = Agent(
        name="Parse Script Runner",
        instructions=instructions_prompt,
        tools=[LocalShellTool()],
        model="gpt-5-minis",
        output_type=Response,
    )

    # Build the prompt
    prompt = f"""
Run the parse.py script to extract evaluation results from the paper with ArXiv ID: {arxiv_id}

The script is located at: {project_root}/extract_evaluation_results/parse.py

Execute the command:
```bash
cd {project_root} && uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id {arxiv_id}
```

After running the script:
1. Check if it succeeded (exit code 0 and "Success: True" in output)
2. Extract the number of evaluations added from Step 7 output
3. Extract the number of duplicates skipped from Step 7 output
4. Report any errors if the script failed

Return your findings in the required JSON format.
"""

    # Run the agent
    logger.info(f"Running agent for ArXiv ID: {arxiv_id}")
    result = await Runner.run(agent, prompt, max_turns=10)

    if result is None:
        raise RuntimeError("Agent returned None")

    # Extract final output
    if hasattr(result, "final_output"):
        agent_output = result.final_output
    else:
        agent_output = result

    if agent_output is None:
        raise RuntimeError("Agent final_output is None")

    # Convert to Response model if needed
    if isinstance(agent_output, Response):
        return agent_output
    elif isinstance(agent_output, dict):
        return Response(**agent_output)
    else:
        # Try to parse as JSON string
        try:
            if isinstance(agent_output, str):
                parsed = json.loads(agent_output)
                return Response(**parsed)
        except json.JSONDecodeError:
            pass

        # Fallback: create response with the output as reasoning
        return Response(
            reasoning=str(agent_output),
            script_succeeded=False,
            errors=[f"Could not parse agent output: {type(agent_output)}"],
        )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run parse.py script via an AI agent and verify results."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        required=False,
        default="2406.09414",
        help="The ArXiv ID of the paper to process",
    )
    args = parser.parse_args()

    try:
        response = await run_agent(args.arxiv_id)

        # Print the response as formatted JSON
        print("\n" + "=" * 60)
        print("AGENT EXECUTION RESULTS")
        print("=" * 60)
        print(json.dumps(response.model_dump(), indent=2))
        print("=" * 60)

        # Exit with error code if script failed
        if not response.script_succeeded:
            exit(1)

    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        print(f"\nError: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
