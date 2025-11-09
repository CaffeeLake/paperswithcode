"""
Step 6: Normalize evaluation results datasets and metrics.

This script normalizes the dataset names and metric names in evaluation results extracted from a paper
by mapping them to canonical dataset names/IDs and metric names from the database based on the outputs
of Step 2 (datasets found in database) and Step 4 (datasets newly added to database).

You can run it like so:

```bash
# Process evaluation results from step_1 using step_2 and step_4 outputs
uv run --env-file backend/keys.env extract_evaluation_results/step_6.py --arxiv_id "2406.09414"
```

The script will:
1. Read step_1, step_2, and step_4 outputs from cache
2. Use an AI agent to normalize dataset names and metric names
3. Build a mapping from original dataset names to canonical DB dataset names and IDs
4. Normalize metrics using existing evaluation conventions and common synonyms
5. Return normalized evaluation results with statistics
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel
from agents import AgentOutputSchema

from extract_evaluation_results.step_base import AgentStep, StepResult
from extract_evaluation_results.tools import get_leaderboard_metrics
from backend.database.connection import db_manager
from backend.models.database import Paper as DBPaper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Step6Input(BaseModel):
    """Input data for Step6."""

    arxiv_id: str
    evaluation_results: list[dict[str, Any]]
    step_2_results: list[dict[str, Any]]
    step_4_results: Optional[list[dict[str, Any]]] = None
    step_5_all_metrics: Optional[dict[str, str]] = (
        None  # Metric name -> direction mapping
    )


class Step6Output(BaseModel):
    """Output data for Step6."""

    normalized: list[dict[str, Any]]
    mapped: int
    unresolved: int
    dataset_mapping: dict[str, dict[str, Any]]


normalizer_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in normalizing evaluation results extracted from research papers. Your responsibility is to map evaluation results to canonical dataset names, IDs, and metric names from our database.

A colleague has already:
1. Extracted evaluation results from a paper (Step 1)
2. Found some datasets in the database (Step 2)
3. Added missing datasets to the database (Step 4)
4. Extracted and added metrics to the database (Step 5)

Your job is to normalize ALL evaluation results by:
1. Mapping dataset names to canonical database names and IDs
2. Normalizing metric names to match existing leaderboard conventions
3. Ensuring paper_id and task_id are populated
4. Marking unresolvable evaluations with _unresolved flag

## Dataset Normalization

Use the step_2_results and step_4_results provided in the prompt to map original dataset names to canonical database information:

- **step_2_results**: Datasets that were found in the database
  - Look for entries with "found": true
  - Extract: dataset ID, canonical name, slug, task_ids, metrics_by_task
  - **CRITICAL**: Use task_ids from step_2_results - these are the correct task associations
  - Use metrics_by_task to see which metrics are allowed for each task-dataset combination

- **step_4_results**: Datasets that were newly added (or already existed)
  - Look for entries with "success": true or "dataset_id" field
  - Extract: dataset ID, canonical name

Create a mapping from original dataset names (case-insensitive) to:
- `dataset_id`: The database ID
- `canonical_name`: The official name in the database
- `task_id`: Use the task_id from step_2_results if available (from dataset.task_ids[0])
  **CRITICAL**: Always use the task_ids from step_2_results for datasets found in step_2.
  These are the correct task associations already in the database. Do NOT infer task_ids.

## Metric Normalization

Metrics often have synonyms or variations. Normalize them to canonical names used in existing evaluations.

### Common Metric Synonyms

Learn these standard mappings:

**Object Detection / Instance Segmentation:**
- "AP" / "Average Precision" / "Box AP" / "Object AP" → "mAP" (most common)
- "Mask AP" / "Segmentation AP" → "Mask mAP"
- "AP50" / "AP at IoU=0.50" → "AP50"
- "AP75" / "AP at IoU=0.75" → "AP75"
- "APs" / "AP small" → "APs"
- "APm" / "AP medium" → "APm"
- "APl" / "AP large" → "APl"

**Image Classification:**
- "Accuracy" / "Top-1 Accuracy" / "Top-1" → "Top-1 Accuracy"
- "Top-5" / "Top-5 Accuracy" → "Top-5 Accuracy"
- "Error Rate" / "Top-1 Error" → "Top-1 Error"

**Speech Recognition:**
- "WER" / "Word Error Rate" → "WER"
- "CER" / "Character Error Rate" → "CER"

**Machine Translation / NLG:**
- "BLEU" / "BLEU-4" → "BLEU"
- "ROUGE" / "ROUGE-L" → "ROUGE-L"

**Question Answering:**
- "F1" / "F1 Score" → "F1"
- "EM" / "Exact Match" → "EM"

### Using get_leaderboard_metrics Tool

For each (task_id, dataset_id) pair, you can call:
```
get_leaderboard_metrics(task_id=X, dataset_id=Y)
```

This will show you:
- What metric names are actually used in existing evaluations
- Frequency of each metric name
- Most common best_metric values

Use this to verify your normalization is correct. If existing evaluations use "mAP" and you see "AP" in the extracted results, normalize to "mAP".

## Required Fields in Normalized Results

Each normalized evaluation must have:

1. **paper_id** (int): Database ID of the paper (lookup from arxiv_id)
2. **task_id** (int): Database ID of the task (from dataset.tasks[0])
3. **dataset_id** (int): Database ID of the dataset
4. **dataset_name** (str): Canonical name from database
5. **metrics** (dict): Dictionary with normalized metric names → values
   - Example: {"mAP": "44.9", "AP50": "64.7"}
6. **best_metric** (str): The primary metric name (normalized)
7. **model_name** (str, optional): Model/method name if available
8. **methodology** (str, optional): Methodology description if available

Also include metadata fields:
- **_original_dataset_name** (str): Original dataset name from extraction
- **_mapping_source** (str): Where mapping came from ("step_2", "step_4_added", etc.)

## Error Handling

If a dataset or metric cannot be normalized:
1. Mark the evaluation with `_unresolved: true`
2. Add `_reason` field explaining why (e.g., "Dataset not found in step_2 or step_4 results")
3. Still include the evaluation in the normalized list so it can be reviewed

## Output Format

Return a Step6Output with:

```python
class Step6Output(BaseModel):
    normalized: list  # List of all normalized evaluation results
    mapped: int  # Count of successfully mapped evaluations
    unresolved: int  # Count of evaluations that couldn't be fully normalized
    dataset_mapping: dict  # Mapping from original names to {id, canonical_name}
```

The `normalized` list should contain all evaluations (both successfully mapped and unresolved).

## Important Notes

1. **Case-insensitive matching**: "coco" should match "COCO"
2. **Preserve all fields**: Keep original fields from extracted results plus add normalized ones
3. **Handle missing data**: If paper_id or task_id cannot be found, mark as unresolved
4. **Metric verification**: Use get_leaderboard_metrics when uncertain about metric names
5. **Multiple metrics**: An evaluation can have multiple metrics in the `metrics` dict, but only one `best_metric`

Process ALL evaluation results, even if some cannot be fully normalized. Mark problematic ones with `_unresolved: true` so they can be reviewed manually.
"""


class Step6(AgentStep[Step6Input, Step6Output]):
    """Agent-based normalization of evaluation results."""

    input_model = Step6Input
    output_model = Step6Output

    def __init__(self):
        super().__init__(
            name="Step6: Evaluation Normalizer",
            description="Normalizes dataset names and metric names in evaluation results",
            instructions=normalizer_prompt,
            tools=[get_leaderboard_metrics],
            model="gpt-5-mini",
            agent_output_type=AgentOutputSchema(Step6Output, strict_json_schema=False),
        )

    async def build_agent_prompt(self, inputs: Step6Input) -> str:
        """Convert Step6Input to agent input prompt with context."""
        logger.info(
            f"Building prompt for {len(inputs.evaluation_results)} evaluation results"
        )

        # Get paper_id from arxiv_id
        paper_id = None
        try:
            session = db_manager.session_local()
            try:
                paper = (
                    session.query(DBPaper)
                    .filter(DBPaper.arxiv_id.like(f"{inputs.arxiv_id}%"))
                    .first()
                )
                if paper:
                    paper_id = paper.id
                    logger.info(
                        f"Found paper_id {paper_id} for arxiv_id {inputs.arxiv_id}"
                    )
                else:
                    logger.warning(
                        f"Could not find paper with arxiv_id {inputs.arxiv_id} in database"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error looking up paper_id: {e}")

        # Format step_2 results
        step_2_text = "### Step 2 Results (Datasets Found in Database)\n\n"
        if inputs.step_2_results:
            step_2_text += "```json\n"
            step_2_text += json.dumps(inputs.step_2_results, indent=2)
            step_2_text += "\n```\n"
        else:
            step_2_text += "No datasets found in step 2.\n"

        # Format step_4 results
        step_4_text = "\n### Step 4 Results (Datasets Newly Added to Database)\n\n"
        if inputs.step_4_results:
            step_4_text += "```json\n"
            step_4_text += json.dumps(inputs.step_4_results, indent=2)
            step_4_text += "\n```\n"
        else:
            step_4_text += "No new datasets added in step 4.\n"

        # Format step_5 results (metrics)
        step_5_text = "\n### Step 5 Results (Metrics in Database)\n\n"
        if inputs.step_5_all_metrics:
            step_5_text += "The following metrics are now available in the database with their directions:\n\n"
            step_5_text += "```json\n"
            step_5_text += json.dumps(inputs.step_5_all_metrics, indent=2)
            step_5_text += "\n```\n"
            step_5_text += "\nUse these metric names and directions when normalizing evaluation results.\n"
        else:
            step_5_text += "No metrics information from step 5. Use get_leaderboard_metrics to check metric names.\n"

        # Format evaluation results
        eval_text = "\n### Evaluation Results to Normalize\n\n"
        eval_text += f"Paper ArXiv ID: {inputs.arxiv_id}\n"
        if paper_id:
            eval_text += f"Paper Database ID: {paper_id}\n"
        else:
            eval_text += (
                "Paper Database ID: NOT FOUND (evaluations will be unresolved)\n"
            )
        eval_text += f"\nTotal evaluation results: {len(inputs.evaluation_results)}\n\n"
        eval_text += "```json\n"
        eval_text += json.dumps(inputs.evaluation_results, indent=2)
        eval_text += "\n```\n"

        # Construct full prompt
        prompt = f"""
{step_2_text}
{step_4_text}
{step_5_text}
{eval_text}

## Your Task

Normalize ALL {len(inputs.evaluation_results)} evaluation results above by:

1. **Dataset Mapping**: Use step_2 and step_4 results to map each dataset name to its database ID and canonical name
2. **Metric Normalization**: Normalize metric names using common synonyms and existing leaderboard conventions
   - Use get_leaderboard_metrics(task_id, dataset_id) to check what metrics are used
3. **Field Population**: Ensure paper_id ({"available: " + str(paper_id) if paper_id else "NOT FOUND"}), task_id, dataset_id, dataset_name are set
4. **Error Handling**: Mark unresolvable evaluations with _unresolved: true

Return a Step6Output with:
- `normalized`: List of all normalized evaluation results (including unresolved ones)
- `mapped`: Count of successfully normalized evaluations
- `unresolved`: Count of evaluations that couldn't be fully normalized
- `dataset_mapping`: Dictionary from original dataset names to {{id, canonical_name}}

Process every evaluation result. Do not skip any.
"""

        return prompt


# Standardized output directory functions
def get_output_dir(arxiv_id: str) -> Path:
    """Get the output directory for a given ArXiv ID."""
    base_dir = (
        Path(__file__).parent.parent / "backend" / "outputs" / "evaluation_results"
    )
    output_dir = base_dir / arxiv_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def read_step_1_output(arxiv_id: str) -> str:
    """Read step_1 output from standardized location."""
    output_dir = get_output_dir(arxiv_id)
    step_1_path = output_dir / "step_1.json"
    if not step_1_path.exists():
        raise FileNotFoundError(f"step_1 output not found at {step_1_path}")
    return step_1_path.read_text()


async def step_6(
    arxiv_id: str,
    evaluation_results: list,
    step_2_results: list,
    step_4_results: Optional[list] = None,
    step_5_all_metrics: Optional[dict] = None,
) -> Optional[Step6Output]:
    """
    Normalize evaluation results datasets and metrics (wrapper for Step6).

    Args:
        arxiv_id: The ArXiv ID of the paper
        evaluation_results: List of evaluation results from step_1
        step_2_results: List of step_2 results (datasets found in database)
        step_4_results: Optional list of step_4 results (datasets newly added to database)
        step_5_all_metrics: Optional dict of metric name -> direction from step_5

    Returns:
        Step6Output with normalized results and statistics, or None if failed
    """
    agent = Step6()
    input_data = Step6Input(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
        step_4_results=step_4_results,
        step_5_all_metrics=step_5_all_metrics,
    )
    result = await agent.run(input_data)

    if not result.success:
        print(f"Step 6 failed: {result.error_message}")
        return None

    return result.outputs


async def main():
    parser = argparse.ArgumentParser(
        description="Normalize evaluation results datasets and metrics using AI agent."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        help="The ArXiv ID of the paper that contains the evaluation results.",
        default="2406.09414",
    )
    args = parser.parse_args()

    arxiv_id = args.arxiv_id

    # Read step_1 output
    step_1_output = read_step_1_output(arxiv_id)
    step_1_data = json.loads(step_1_output)
    evaluation_results = step_1_data.get("evaluation_results", [])

    if not evaluation_results:
        print("No evaluation results found in step_1 output")
        return {"normalized": [], "mapped": 0, "unresolved": 0, "dataset_mapping": {}}

    # Read step_2 output
    output_dir = get_output_dir(arxiv_id)
    step_2_path = output_dir / "step_2_results.json"
    if not step_2_path.exists():
        print(f"Warning: step_2 output not found at {step_2_path}")
        step_2_results = []
    else:
        step_2_results = json.loads(step_2_path.read_text())

    # Read step_4 output (optional)
    step_4_path = output_dir / "step_4_results.json"
    if step_4_path.exists():
        step_4_results = json.loads(step_4_path.read_text())
    else:
        step_4_results = []

    # Read step_5 output (optional)
    step_5_path = output_dir / "step_5_metrics.json"
    step_5_all_metrics = None
    if step_5_path.exists():
        step_5_data = json.loads(step_5_path.read_text())
        step_5_all_metrics = step_5_data.get("all_metrics")

    # Run normalization
    result = await step_6(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
        step_4_results=step_4_results,
        step_5_all_metrics=step_5_all_metrics,
    )

    if not result:
        print("Normalization failed")
        return None

    # Write output
    output_path = output_dir / "step_6_normalized.json"
    output_path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    )
    print(f"✓ Normalized results written to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("NORMALIZATION SUMMARY")
    print("=" * 60)
    print(f"Total evaluation results: {len(evaluation_results)}")
    print(f"Successfully mapped: {result.mapped}")
    print(f"Unresolved: {result.unresolved}")
    print(f"\nDataset mappings used: {len(result.dataset_mapping)}")
    for original_name, mapping in result.dataset_mapping.items():
        print(
            f"  - '{original_name}' -> '{mapping['canonical_name']}' (ID: {mapping['id']})"
        )
    print("=" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\nNormalized evaluation results:")
        print(json.dumps(result.normalized[:3], indent=2))  # Show first 3
        if len(result.normalized) > 3:
            print(f"... and {len(result.normalized) - 3} more")


# Workflow integration
class Step6WorkflowStep:
    """Workflow step wrapper for Step6."""

    name = "Step6WorkflowStep"

    def __init__(self):
        self.step = Step6()

    async def execute(self, state):
        """
        Execute Step6 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str
        - evaluation_results: list
        - step_2_results: list
        - step_4_results: list (optional)
        - all_metrics: dict (optional, from step_5)

        Writes to state.data:
        - normalized: list of normalized evaluation results
        - mapped: int - number of mapped evaluations
        - unresolved: int - number of unresolved evaluations
        - dataset_mapping: dict - mapping from original to canonical names
        - step_6_normalized: dict - complete normalization result
        """
        # Build inputs from state.data
        evaluation_results = state.data.get("evaluation_results", [])

        # Early return if no evaluation results to process
        if not evaluation_results:
            logger.info("No evaluation results to normalize. Skipping Step 6.")
            empty_output = Step6Output(
                normalized=[], mapped=0, unresolved=0, dataset_mapping={}
            )
            return StepResult(
                success=True,
                outputs=empty_output,
            )

        inputs = {
            "arxiv_id": state.data.get("arxiv_id", state.arxiv_id),
            "evaluation_results": evaluation_results,
            "step_2_results": state.data.get("step_2_results", []),
            "step_4_results": state.data.get("step_4_results"),
            "step_5_all_metrics": state.data.get("all_metrics"),
        }

        # Execute the agent step
        result = await self.step.run(inputs)

        return result
