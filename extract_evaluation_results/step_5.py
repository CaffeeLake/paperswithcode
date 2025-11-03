"""
This script defines an agent that can add evaluation results to the database.

You can run it like so:

```bash
# Using a file with aligned evaluation results
uv run --env-file backend/keys.env extract_evaluation_results/step_5.py --arxiv_id "2406.09414" --aligned_results_file "aligned_results_2406.09414.json"

# Using aligned results as JSON string
uv run --env-file backend/keys.env extract_evaluation_results/step_5.py --arxiv_id "2406.09414" --aligned_results '[{"paper_id": 123, "task_id": 2, "dataset_id": 72, "metrics": {"AP": "44.9"}, "best_metric": "AP", "model_name": "DETR"}]'
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
from pathlib import Path
from typing import Optional

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.utils.logging_utils import async_export_txt

from sqlalchemy.orm import Session

from agents import Agent, function_tool, Runner
from backend.models.database import (
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    Paper as DBPaper,
)


evaluation_adder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in managing evaluation results in a SQL database.
A colleague of yours has extracted evaluation results from a paper and identified the datasets, tasks, and metrics.
Your responsibility includes adding these evaluation results to the database.

## CRITICAL: Understanding Leaderboards as Triples

Leaderboards are defined by **(task, dataset, metric)** triples. For example:
- (Image Classification, ImageNet-1k, Top-1 Accuracy)
- (Image Classification, ImageNet-1k, Top-5 Accuracy)
- (Image Generation, ImageNet-1k, FID)
- (Object Detection, COCO, AP)
- (Object Detection, COCO, AP50)

Each evaluation result belongs to a specific leaderboard triple via the `best_metric` field. The same model can have multiple evaluation records for different metrics on the same dataset (e.g., one for AP, one for AP50).

## Important Rules

1. **Duplicate Prevention**: Before adding an evaluation, check if an evaluation already exists with the same:
   - paper_id
   - task_id
   - dataset_id
   - model_name
   - best_metric

   If such an evaluation exists, do NOT create a duplicate. Return a message indicating the evaluation already exists.

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
   - metrics (dict): Dictionary of metric names to values (e.g., {"AP": "44.9", "AP50": "64.7"})
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

When successfully adding an evaluation, return a JSON string with the evaluation details:
```json
{
  "success": true,
  "evaluation_id": 123,
  "paper_id": 456,
  "task_id": 2,
  "dataset_id": 72,
  "model_name": "DETR",
  "metrics": {"AP": "44.9", "AP50": "64.7"},
  "best_metric": "AP",
  "best_rank": 1
}
```

If there's an error (duplicate, invalid metric, etc.), return a clear error message explaining what went wrong.

**IMPORTANT**: Always check for duplicates before attempting to add an evaluation. Use get_leaderboard_metrics to verify valid metrics if needed.
"""


@function_tool
async def get_leaderboard_metrics(task_id: int, dataset_id: int) -> str:
    """Get the list of allowed metrics for a specific leaderboard (task + dataset).

    This tool helps you determine which metrics are valid for a given (task, dataset) pair.
    Each (task, dataset, metric) triple defines a unique leaderboard.

    Args:
        task_id: The ID of the task
        dataset_id: The ID of the dataset

    Returns:
        A formatted string with the allowed metrics for this leaderboard, including their directions (higher/lower is better).
        If no metrics are configured, returns a message indicating all metrics are allowed (backwards compatibility).
    """
    session: Session = db_manager.session_local()
    service = LeaderboardMetricService(session)

    try:
        result = service.get_leaderboard_metrics(task_id, dataset_id)

        if not result["metrics"]:
            response = (
                f"No specific metrics configured for leaderboard (Task {task_id}, Dataset {dataset_id}). "
                f"All metrics are allowed (backwards compatibility mode)."
            )
        else:
            response = f"Allowed metrics for leaderboard (Task {result['task_name']}, Dataset {result['dataset_name']}):\n"
            for metric in result["metrics"]:
                direction = (
                    "higher is better"
                    if metric["metric_direction"] == "higher_is_better"
                    else "lower is better"
                )
                response += f"  - {metric['metric_name']} ({direction})\n"

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except ValueError as e:
        session.close()
        error_msg = f"Error: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg
    except Exception as e:
        session.close()
        error_msg = f"Error retrieving leaderboard metrics: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg


@function_tool
async def add_evaluation_result(
    paper_id: int,
    task_id: int,
    dataset_id: int,
    metrics: dict,
    best_metric: str,
    model_name: Optional[str] = None,
    methodology: Optional[str] = None,
    uses_additional_data: bool = False,
    evaluated_on: Optional[str] = None,
    external_source_url: Optional[str] = None,
) -> str:
    """Add a new evaluation result to the database.

    This tool adds an evaluation result to a specific leaderboard triple (task, dataset, metric).
    The evaluation will be automatically ranked on the leaderboard defined by (task_id, dataset_id, best_metric).

    Args:
        paper_id: The ID of the paper that produced this evaluation
        task_id: The ID of the task being evaluated
        dataset_id: The ID of the dataset used for evaluation
        metrics: Dictionary of metric names to values (e.g., {"AP": "44.9", "AP50": "64.7"})
        best_metric: The name of the best performing metric (must be in the metrics dict)
        model_name: Name of the model/method (optional)
        methodology: Description of the methodology (optional)
        uses_additional_data: Whether additional data was used beyond the dataset (default: False)
        evaluated_on: Date when evaluation was performed in YYYY-MM-DD format (optional)
        external_source_url: URL to external source like a competition (optional)

    Returns:
        A success message with evaluation details, or an error message if creation failed.
    """
    # Log tool call for debugging
    print(
        f"[TOOL CALL] add_evaluation_result(paper_id={paper_id}, task_id={task_id}, "
        f"dataset_id={dataset_id}, metrics={metrics}, best_metric={best_metric}, "
        f"model_name={model_name})"
    )

    session: Session = db_manager.session_local()

    try:
        # 1. Check if paper exists
        paper = session.query(DBPaper).filter(DBPaper.id == paper_id).first()
        if not paper:
            session.close()
            return f"Error: Paper with ID {paper_id} not found in database"

        # 2. Validate and normalize best_metric
        # First, check if best_metric is in the metrics dict
        metric_keys = list(metrics.keys())
        best_metric_lower = best_metric.lower()

        # Find matching metric in database (case-insensitive)
        metric_def = (
            session.query(DBMetric).filter(DBMetric.name.ilike(best_metric)).first()
        )
        if not metric_def:
            session.close()
            return (
                f"Error: Metric '{best_metric}' not found in metrics table. "
                f"Available metrics in evaluation: {', '.join(metric_keys)}. "
                f"Please ensure the metric name is correct and exists in the database."
            )

        # Use the canonical name from the database
        normalized_best_metric = metric_def.name

        # Verify best_metric is in the metrics dict (case-insensitive)
        if not any(key.lower() == best_metric_lower for key in metric_keys):
            session.close()
            return (
                f"Error: best_metric '{best_metric}' must be one of the metrics in the metrics dictionary. "
                f"Available metrics: {', '.join(metric_keys)}"
            )

        # 3. Check for duplicates (including best_metric in the key)
        existing = (
            session.query(DBEvaluation)
            .filter(
                DBEvaluation.paper_id == paper_id,
                DBEvaluation.task_id == task_id,
                DBEvaluation.dataset_id == dataset_id,
                DBEvaluation.model_name == model_name,
                DBEvaluation.best_metric == normalized_best_metric,
            )
            .first()
        )

        if existing:
            session.close()
            return (
                f"Evaluation already exists: ID={existing.id}, Paper ID={paper_id}, "
                f"Task ID={task_id}, Dataset ID={dataset_id}, Model='{model_name}', "
                f"Best Metric='{normalized_best_metric}'. "
                f"Duplicates are not allowed for the same (paper, task, dataset, model, best_metric) combination."
            )

        # 4. Validate all metrics exist in database
        metric_names_to_check = list(metrics.keys())
        invalid_metrics = []
        for metric_name in metric_names_to_check:
            metric_check = (
                session.query(DBMetric).filter(DBMetric.name.ilike(metric_name)).first()
            )
            if not metric_check:
                invalid_metrics.append(metric_name)

        if invalid_metrics:
            session.close()
            return (
                f"Error: The following metrics are not found in the metrics table: {', '.join(invalid_metrics)}. "
                f"Please ensure all metric names are correct and exist in the database."
            )

        # 5. Normalize metric names in the metrics dict to canonical form
        normalized_metrics = {}
        for metric_key, metric_value in metrics.items():
            metric_def = (
                session.query(DBMetric).filter(DBMetric.name.ilike(metric_key)).first()
            )
            if metric_def:
                normalized_metrics[metric_def.name] = metric_value
            else:
                # This shouldn't happen due to validation above, but handle it gracefully
                normalized_metrics[metric_key] = metric_value

        # 6. Add the evaluation using the service layer
        evaluation_service = EvaluationService(session)
        evaluation = evaluation_service.create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            metrics=normalized_metrics,
            model_name=model_name,
            methodology=methodology,
            uses_additional_data=uses_additional_data,
            best_metric=normalized_best_metric,
            evaluated_on=evaluated_on,
            external_source_url=external_source_url,
        )

        # Format success response
        response = (
            f"✓ Successfully created evaluation: ID={evaluation.id}, Paper ID={paper_id}, "
            f"Task ID={task_id}, Dataset ID={dataset_id}, Model='{model_name}', "
            f"Metrics={normalized_metrics}, Best Metric='{normalized_best_metric}', "
            f"Best Rank={evaluation.best_rank}"
        )

        session.close()
        print(f"[TOOL RESULT] {response}")
        return response

    except ValueError as e:
        session.close()
        error_msg = f"Validation error: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg
    except Exception as e:
        session.close()
        error_msg = f"Error creating evaluation: {str(e)}"
        print(f"[TOOL RESULT] {error_msg}")
        return error_msg


async def create_evaluation_adder_agent() -> Agent:
    """Create the evaluation adder agent."""
    return Agent(
        name="Evaluation Adder",
        instructions=evaluation_adder_prompt,
        tools=[add_evaluation_result, get_leaderboard_metrics],
    )


def read_aligned_results_file(filename: str) -> str:
    """Read the aligned evaluation results file."""
    # Try backend/outputs first, then extract_evaluation_results
    output_dir = Path(__file__).parent.parent / "backend" / "outputs"
    file_path = output_dir / filename
    if not file_path.exists():
        # Fallback to extract_evaluation_results directory
        file_path = Path(__file__).parent / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find aligned results file: {filename}")
    return file_path.read_text()


async def step_5(
    arxiv_id: str,
    aligned_evaluation_results: list,
    paper_details: str,
) -> str:
    """Process aligned evaluation results to add them to the database.

    Args:
        arxiv_id: The ArXiv ID of the paper containing the evaluation results
        aligned_evaluation_results: List of aligned evaluation results with paper_id, task_id, dataset_id
        paper_details: Formatted paper details (title, authors, abstract)

    Returns:
        The result from the evaluation adder agent
    """
    print(f"Processing {len(aligned_evaluation_results)} evaluation results")

    prompt = f"""
## Paper details
{paper_details}

## Evaluation results to add

The following evaluation results have been extracted and aligned with the database (paper_id, task_id, dataset_id):
{json.dumps(aligned_evaluation_results, indent=2)}

Please add these evaluation results to the database. For each evaluation result:
1. Check if it already exists (duplicate check)
2. Validate that all metrics exist in the database
3. Ensure best_metric is valid and in the metrics dictionary
4. Add the evaluation result using the add_evaluation_result tool

If any evaluation result cannot be added, provide a clear error message explaining why.
"""

    # Run the evaluation adder agent
    evaluation_adder_agent = await create_evaluation_adder_agent()
    result = await Runner.run(evaluation_adder_agent, prompt)
    return result.final_output


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
    if args.aligned_results_file:
        aligned_results_content = read_aligned_results_file(args.aligned_results_file)
        aligned_results_data = json.loads(aligned_results_content)
        # Try different possible keys
        aligned_evaluation_results = aligned_results_data.get(
            "aligned_evaluation_results",
            aligned_results_data.get("evaluation_results", []),
        )
    elif args.aligned_results:
        aligned_results_data = json.loads(args.aligned_results)
        aligned_evaluation_results = aligned_results_data.get(
            "aligned_evaluation_results",
            aligned_results_data if isinstance(aligned_results_data, list) else [],
        )
    else:
        print(
            "Error: Either --aligned_results_file or --aligned_results must be provided"
        )
        return "Error: No aligned evaluation results provided"

    if not aligned_evaluation_results:
        print("No aligned evaluation results found")
        return "No aligned evaluation results found"

    # Get paper details
    from extract_evaluation_results.step_2 import get_paper_details

    paper_details = await get_paper_details(arxiv_id)

    await async_export_txt(
        filename=f"step_5_{arxiv_id}",
        value=f"Processing {len(aligned_evaluation_results)} evaluation results",
    )

    # Process the evaluation results
    result = await step_5(
        arxiv_id=arxiv_id,
        aligned_evaluation_results=aligned_evaluation_results,
        paper_details=paper_details,
    )
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    print("Result: ", result)
