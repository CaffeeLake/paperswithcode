"""
Step 7: Add evaluation results to the database.

This script defines an agent that can add evaluation results to the database.

You can run it like so:

```bash
# Using a file with aligned evaluation results
uv run --env-file backend/keys.env extract_evaluation_results/step_7.py --arxiv_id "2406.09414" --aligned_results_file "aligned_results_2406.09414.json"

# Using aligned results as JSON string
uv run --env-file backend/keys.env extract_evaluation_results/step_7.py --arxiv_id "2406.09414" --aligned_results '[{"paper_id": 123, "task_id": 2, "dataset_id": 72, "metrics": {"AP": "44.9"}, "best_metric": "AP", "model_name": "DETR"}]'
```

The aligned evaluation results should contain:
- paper_id: The ID of the paper in the database
- task_id: The ID of the task
- dataset_id: The ID of the dataset
- metrics: Dictionary of metric names to values (e.g., {"AP": "44.9", "AP50": "64.7"})
- best_metric: The name of the best performing metric (must be in the metrics dict)
- model_name: Optional name of the model/method
- methodology: Optional description of the methodology
- uses_additional_data: Optional boolean (default: False)
- evaluated_on: Optional date in YYYY-MM-DD format
- external_source_url: Optional URL to external source
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.utils.logging_utils import async_export_txt
from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.utils import get_formatted_tasks_list
from extract_evaluation_results.tools import (
    get_leaderboard_metrics,
    add_evaluation_result,
    add_metric_to_leaderboard,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_BASE = PROJECT_ROOT / "backend" / "outputs"
STEP7_INPUT_FILENAME = "step_7_aligned_results.json"
STEP7_OUTPUT_FILENAME = "step_7_cli.json"


class EvaluationResult(BaseModel):
    success: bool
    evaluation_id: Optional[int] = None
    paper_id: Optional[int] = None
    task_id: Optional[int] = None
    dataset_id: Optional[int] = None
    model_name: Optional[str] = None
    metrics: Optional[str] = None
    best_metric: Optional[str] = None
    best_rank: Optional[int] = None


evaluation_adder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in managing evaluation results in a SQL database.
A colleague of yours has extracted evaluation results from a paper and identified the datasets, tasks, and metrics from leaderboard tables.
Your responsibility includes adding these evaluation results to the database.

## Context: Available Tasks and Datasets

Below is a list of tasks currently in the database along with their associated datasets. This provides context about the current information landscape of the PapersWithCode app:

{tasks_list}

Use this context to better understand which tasks and datasets are commonly used together, which can help you validate that the evaluation results are being added to the correct leaderboards.

## CRITICAL: Understanding Leaderboards as Triples

Leaderboards are defined by **(task, dataset, metric)** triples. For example:
- (Image Classification, ImageNet-1k, Top-1 Accuracy)
- (Image Classification, ImageNet-1k, Top-5 Accuracy)
- (Image Generation, ImageNet-1k, FID)
- (Object Detection, COCO, AP)
- (Object Detection, COCO, AP50)

Each evaluation result belongs to a specific leaderboard triple via the `best_metric` field. The same model can have multiple evaluation records for different metrics on the same dataset (e.g., one for AP, one for AP50).

## Leaderboard Auto-Creation (CRITICAL)

Before adding an evaluation, you MUST ensure the leaderboard exists:

1. **Check Leaderboard**: Use `get_leaderboard_metrics(task_id, dataset_id)` to check if metrics are configured
2. **Create if Missing**: If the result shows "No specific metrics configured" (empty metrics list), create leaderboard entries:
   - Extract all metric names from the `metrics` dictionary in the evaluation result
   - For each metric name, call `add_metric_to_leaderboard(task_id, dataset_id, metric_name)`
   - This ensures the leaderboard is properly configured before adding evaluations
3. **Then Add Evaluation**: Once leaderboard is configured, proceed with `add_evaluation_result`

**Example Flow**:
```
1. Check: get_leaderboard_metrics(task_id=13, dataset_id=384)
   → Returns: "No specific metrics configured for leaderboard"

2. Create leaderboard for metrics in evaluation: {{"PSNR": "21.33", "SSIM": "0.711"}}
   → Call: add_metric_to_leaderboard(task_id=13, dataset_id=384, metric_name="PSNR")
   → Call: add_metric_to_leaderboard(task_id=13, dataset_id=384, metric_name="SSIM")

3. Add evaluation: add_evaluation_result(...)
   → Now succeeds!
```

**When to create leaderboards**:
- Always check first with `get_leaderboard_metrics`
- Only create if "No specific metrics configured" appears in the result
- Create entries for ALL metrics in the evaluation's `metrics` dictionary
- After creating leaderboard entries, proceed with adding the evaluation

## Important Rules

1. **Duplicate Prevention** (CRITICAL): Before adding an evaluation, you MUST check if an evaluation already exists. The prompt will include a list of existing evaluations for the paper. Compare each evaluation you're trying to add against this list using the following criteria:
   - paper_id
   - task_id
   - dataset_id
   - model_name
   - best_metric

   If an evaluation with the same combination of these fields already exists in the list provided, do NOT attempt to add it. Skip it and report that it's a duplicate. The tool `add_evaluation_result` also performs duplicate checking, but you should avoid calling it for duplicates to save API calls and improve efficiency.

2. **Metric Validation**:
   - All metrics in the `metrics` dictionary must exist in the `metrics` table
   - The `best_metric` must be one of the metrics in the `metrics` dictionary
   - Metric names are case-insensitive (e.g., "ap" matches "AP")
   - Metric names will be normalized to the canonical form from the database

3. **Leaderboard Triple Validation**:
   - The (task, dataset, metric) triple must be valid
   - Use `get_leaderboard_metrics` to check which metrics are allowed for a leaderboard
   - If no metrics are configured for a leaderboard, all metrics are allowed (backwards compatibility)

4. **Required Fields**:
   - paper_id (int): The ID of the paper
   - task_id (int): The ID of the task
   - dataset_id (int): The ID of the dataset
   - metrics (str): JSON string with dictionary of metric names to values (e.g., '{{"AP": "44.9", "AP50": "64.7"}}')
   - best_metric (str): The name of the best performing metric (must be in the metrics dict)

5. **Optional Fields**:
   - model_name (str): Name of the model/method
   - methodology (str): Description of the methodology
   - uses_additional_data (bool): Whether additional data was used beyond the dataset
   - evaluated_on (str): Date when evaluation was performed (YYYY-MM-DD format)
   - external_source_url (str): URL to external source (e.g., competition)

## Checking Valid Metrics for a Leaderboard

Before adding an evaluation, you can use the get_leaderboard_metrics tool to check which metrics are allowed
for a specific (task, dataset) pair. This helps you choose the correct best_metric value.

## Output Format

When successfully adding an evaluation, return the following:

```python
class EvaluationResult(BaseModel):
    success: bool
    evaluation_id: Optional[int] = None
    paper_id: Optional[int] = None
    task_id: Optional[int] = None
    dataset_id: Optional[int] = None
    model_name: Optional[str] = None
    metrics: Optional[str] = None
    best_metric: Optional[str] = None
    best_rank: Optional[int] = None
```

Return the response as a JSON string. Do not include any other text in your response.

**IMPORTANT**: Always check for duplicates before attempting to add an evaluation. Use get_leaderboard_metrics to verify valid metrics if needed.
"""


class Step7Input(BaseModel):
    """Input data for Step7."""

    arxiv_id: str
    aligned_evaluation_results: list
    paper_details: str


# Output model (alias to EvaluationResult for clarity)
Step7Output = EvaluationResult


class Step7(AgentStep[Step7Input, Step7Output]):
    """Agent-based step for adding evaluation results to the database."""

    input_model = Step7Input
    output_model = Step7Output

    def __init__(self):
        # Format instructions with tasks list
        tasks_list = get_formatted_tasks_list()
        formatted_instructions = evaluation_adder_prompt.format(tasks_list=tasks_list)

        super().__init__(
            name="Step7: Evaluation Adder",
            description="Adds evaluation results to the database with validation",
            instructions=formatted_instructions,
            tools=[
                add_evaluation_result,
                get_leaderboard_metrics,
                add_metric_to_leaderboard,
            ],
            model="gpt-5-mini",
            agent_output_type=EvaluationResult,
            max_turns=30,  # Increased for processing multiple evaluation results
        )

    async def build_agent_prompt(self, inputs: Step7Input) -> str:
        """
        Convert Step7Input to agent input prompt.
        """
        print(f"Processing {len(inputs.aligned_evaluation_results)} evaluation results")

        # Get existing evaluations for this paper to prevent duplicates
        existing_evaluations = get_existing_evaluations_for_paper(inputs.arxiv_id)
        print(
            f"Found {len(existing_evaluations)} existing evaluation(s) for this paper"
        )

        # Format existing evaluations for the prompt
        existing_evaluations_text = ""
        if existing_evaluations:
            existing_evaluations_text = f"""
## Existing evaluation results for this paper

The following evaluation results already exist in the database for this paper. **DO NOT** add duplicates of these evaluations:

{json.dumps(existing_evaluations, indent=2)}

**Duplicate Detection**: An evaluation is considered a duplicate if it has the same:
- paper_id
- task_id
- dataset_id
- model_name
- best_metric

Before adding any evaluation, carefully compare it against the existing evaluations above. If a match is found, skip that evaluation and report that it already exists.
"""
        else:
            existing_evaluations_text = """
## Existing evaluation results for this paper

No existing evaluation results found for this paper. You can proceed to add all evaluation results.
"""

        prompt = f"""
## Paper details
{inputs.paper_details}
{existing_evaluations_text}

## Evaluation results to add

The following evaluation results have been extracted and aligned with the database (paper_id, task_id, dataset_id):
{json.dumps(inputs.aligned_evaluation_results, indent=2)}

Please add these evaluation results to the database. For each evaluation result:
1. **First, check if it already exists** by comparing against the existing evaluations listed above (duplicate check)
2. If it already exists, skip it and report that it's a duplicate
3. Validate that all metrics exist in the database
4. Ensure best_metric is valid and in the metrics dictionary
5. Add the evaluation result using the add_evaluation_result tool (only if it doesn't already exist)

**IMPORTANT**: When calling add_evaluation_result, convert the metrics dictionary to a JSON string.
For example, if metrics is {{"AP": "44.9", "AP50": "64.7"}}, pass it as '{{"AP": "44.9", "AP50": "64.7"}}'.

If any evaluation result cannot be added, provide a clear error message explaining why.
"""
        return prompt


def read_aligned_results_file(filename: str) -> str:
    """Read the aligned evaluation results file."""
    # Handle absolute paths
    if Path(filename).is_absolute():
        file_path = Path(filename)
    # Handle relative paths that start with "backend/"
    elif filename.startswith("backend/"):
        file_path = PROJECT_ROOT / filename
    # Handle relative paths that start with "extract_evaluation_results/"
    elif filename.startswith("extract_evaluation_results/"):
        file_path = PROJECT_ROOT / filename
    # Handle just filenames - try in OUTPUTS_BASE first
    else:
        output_dir = OUTPUTS_BASE
        file_path = output_dir / filename
        if not file_path.exists():
            # Fallback to extract_evaluation_results directory
            file_path = Path(__file__).parent / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Could not find aligned results file: {filename}")
    return file_path.read_text()


def get_output_dir(arxiv_id: str) -> Path:
    """Return (and create) the output directory for an ArXiv ID."""
    output_dir = OUTPUTS_BASE / "evaluation_results" / arxiv_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_step_7_cli_output(arxiv_id: str, payload: dict) -> Path:
    """Write the Step 7 CLI output payload to disk for downstream consumers."""
    output_dir = get_output_dir(arxiv_id)
    output_path = output_dir / STEP7_OUTPUT_FILENAME
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("Step 7 CLI output written to %s", output_path)
    return output_path


def extract_aligned_results(data: Any) -> list:
    """Normalize aligned results payloads from various keys."""
    if isinstance(data, dict):
        for key in (
            "aligned_evaluation_results",
            "normalized",
            "evaluation_results",
            "results",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return value
    elif isinstance(data, list):
        return data
    return []


def filter_aligned_results(aligned_results: list[dict]) -> list[dict]:
    """Remove unresolved entries before processing."""
    filtered = [
        result
        for result in aligned_results
        if isinstance(result, dict) and not result.get("_unresolved", False)
    ]
    skipped = len(aligned_results) - len(filtered)
    if skipped > 0:
        logger.info("Filtered %d unresolved evaluation(s) from Step 7 input", skipped)
    return filtered


def get_existing_evaluations_for_paper(arxiv_id: str) -> list[dict]:
    """Get existing evaluation results for a paper by ArXiv ID.

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        List of dictionaries containing existing evaluation details for duplicate detection
    """
    session: Session = db_manager.session_local()
    try:
        # Get paper_id from arxiv_id
        paper_service = PaperService(session)
        try:
            paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
            paper_id = int(paper.id)
        except Exception:
            # Paper not found, return empty list
            session.close()
            return []

        # Get existing evaluations for this paper
        evaluation_service = EvaluationService(session)
        evaluations_result = evaluation_service.get_evaluations(
            paper_id=paper_id,
            page_size=1000,  # Get all evaluations (reasonable limit)
        )

        # Format evaluations for duplicate detection
        existing_evaluations = []
        for eval_obj in evaluations_result.results:
            existing_evaluations.append(
                {
                    "paper_id": int(eval_obj.paper_id),
                    "task_id": int(eval_obj.task_id),
                    "dataset_id": int(eval_obj.dataset_id),
                    "model_name": eval_obj.model_name,
                    "best_metric": eval_obj.best_metric,
                    "metrics": eval_obj.metrics,
                    "task_name": eval_obj.task_name,
                    "dataset_name": eval_obj.dataset_name,
                }
            )

        session.close()
        return existing_evaluations

    except Exception as e:
        session.close()
        print(f"Error fetching existing evaluations: {e}")
        return []


async def step_7(
    arxiv_id: str,
    aligned_evaluation_results: list,
    paper_details: str,
) -> Optional[EvaluationResult]:
    """Step 7: Process aligned evaluation results to add them to the database (wrapper for Step7).

    Args:
        arxiv_id: The ArXiv ID of the paper containing the evaluation results
        aligned_evaluation_results: List of aligned evaluation results with paper_id, task_id, dataset_id
        paper_details: Formatted paper details (title, authors, abstract)

    Returns:
        The result from the evaluation adder agent, or None if failed
    """
    agent = Step7()
    input_data = Step7Input(
        arxiv_id=arxiv_id,
        aligned_evaluation_results=aligned_evaluation_results,
        paper_details=paper_details,
    )
    result = await agent.run(input_data)

    if not result.success:
        print(f"Step 7 failed: {result.error_message}")
        return None

    # result.outputs is now a Step7Output (EvaluationResult) model
    return result.outputs


async def main():
    parser = argparse.ArgumentParser(
        description="Add evaluation results to the database using a set of AI agents."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper that contains the evaluation results.",
        default="2406.09414",
    )
    parser.add_argument(
        "--aligned_results_file",
        type=str,
        help="The file containing aligned evaluation results (JSON format with paper_id, task_id, dataset_id).",
        default=None,
    )
    parser.add_argument(
        "--aligned_results",
        type=str,
        help="Aligned evaluation results as JSON string (alternative to --aligned_results_file).",
        default=None,
    )
    args = parser.parse_args()

    arxiv_id = args.arxiv_id

    # Get aligned evaluation results from file or direct input
    aligned_evaluation_results: list[dict] = []
    if args.aligned_results_file:
        aligned_results_content = read_aligned_results_file(args.aligned_results_file)
        aligned_results_data = json.loads(aligned_results_content)
        aligned_evaluation_results = extract_aligned_results(aligned_results_data)
    elif args.aligned_results:
        aligned_results_data = json.loads(args.aligned_results)
        aligned_evaluation_results = extract_aligned_results(aligned_results_data)
    else:
        message = (
            "Error: Either --aligned_results_file or --aligned_results must be provided"
        )
        print(message)
        write_step_7_cli_output(arxiv_id, {"success": False, "error_message": message})
        return {"success": False, "error_message": message}

    aligned_evaluation_results = filter_aligned_results(aligned_evaluation_results)

    if not aligned_evaluation_results:
        message = "No aligned evaluation results found"
        print(message)
        write_step_7_cli_output(arxiv_id, {"success": False, "error_message": message})
        return {"success": False, "error_message": message}

    # Get paper details
    from extract_evaluation_results.utils import get_paper_details

    paper_details = await get_paper_details(arxiv_id)

    await async_export_txt(
        filename=f"step_7_{arxiv_id}",
        value=f"Processing {len(aligned_evaluation_results)} evaluation results",
        arxiv_id=arxiv_id,
    )

    # Process the evaluation results
    result = await step_7(
        arxiv_id=arxiv_id,
        aligned_evaluation_results=aligned_evaluation_results,
        paper_details=paper_details,
    )

    if not result:
        payload = {"success": False, "error_message": "Step 7 agent failed"}
    else:
        payload = result.model_dump()

    write_step_7_cli_output(arxiv_id, payload)
    return payload


if __name__ == "__main__":
    result = asyncio.run(main())
    print("Result: ", result)


# Workflow integration
class Step7WorkflowOutput(BaseModel):
    """Workflow-friendly wrapper for Step 7 results."""

    step_7_result: Optional[dict] = None
    step_7_error: Optional[str] = None


class Step7WorkflowStep:
    """Workflow step wrapper for Step7."""

    name = "Step7WorkflowStep"

    def __init__(self):
        self.project_root = PROJECT_ROOT

    async def execute(self, state):
        """
        Execute Step7 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str
        - normalized: list (aligned evaluation results from step 6)

        Writes to state.data:
        - step_7_result: dict with evaluation insertion details
        - step_7_error: error message if failed
        """
        from extract_evaluation_results.step_base import StepResult

        arxiv_id = state.data.get("arxiv_id", state.arxiv_id)
        normalized_results = state.data.get("normalized", []) or []
        aligned_results = filter_aligned_results(normalized_results)

        if not aligned_results:
            logger.info("No aligned evaluation results to add. Skipping Step 7.")
            payload = {
                "success": True,
                "message": "No aligned evaluation results to add",
            }
            write_step_7_cli_output(arxiv_id, payload)
            output = Step7WorkflowOutput(step_7_result=payload, step_7_error=None)
            return StepResult(success=True, outputs=output)

        output_dir = get_output_dir(arxiv_id)
        input_path = output_dir / STEP7_INPUT_FILENAME
        input_payload = {"aligned_evaluation_results": aligned_results}
        input_path.write_text(json.dumps(input_payload, ensure_ascii=False, indent=2))
        logger.info(
            "Step7: Prepared %d aligned evaluation(s) at %s",
            len(aligned_results),
            input_path,
        )

        cmd = [
            sys.executable,
            "extract_evaluation_results/step_7.py",
            "--arxiv_id",
            arxiv_id,
            "--aligned_results_file",
            str(input_path.relative_to(self.project_root)),
        ]

        try:
            subprocess.run(cmd, check=True, cwd=self.project_root)
        except subprocess.CalledProcessError as exc:
            error_message = f"Step 7 subprocess failed with exit code {exc.returncode}"
            logger.error(error_message)
            output = Step7WorkflowOutput(step_7_result=None, step_7_error=error_message)
            return StepResult(
                success=False,
                outputs=output,
                error_message=error_message,
            )

        cli_output_path = output_dir / STEP7_OUTPUT_FILENAME
        if not cli_output_path.exists():
            error_message = f"Step 7 output file not found at {cli_output_path}"
            logger.error(error_message)
            output = Step7WorkflowOutput(step_7_result=None, step_7_error=error_message)
            return StepResult(
                success=False,
                outputs=output,
                error_message=error_message,
            )

        try:
            cli_data = json.loads(cli_output_path.read_text())
        except Exception as exc:
            error_message = f"Failed to parse Step 7 output: {exc}"
            logger.error(error_message)
            output = Step7WorkflowOutput(step_7_result=None, step_7_error=error_message)
            return StepResult(
                success=False,
                outputs=output,
                error_message=error_message,
            )

        step_success = cli_data.get("success")
        if step_success is None:
            step_success = bool(cli_data)

        error_message = None if step_success else cli_data.get("error_message")
        output = Step7WorkflowOutput(
            step_7_result=cli_data or None,
            step_7_error=error_message,
        )

        return StepResult(
            success=bool(step_success),
            outputs=output,
            error_message=error_message or "",
        )
