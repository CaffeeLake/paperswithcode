"""
Step 5: Extract and manage metrics from evaluation results.

This script extracts unique metric names from evaluation results and ensures they exist
in the database. If metrics are missing, it intelligently determines their direction
(higher_is_better or lower_is_better) and adds them to the database.

You can run it like so:

```bash
# Process evaluation results from step_1 to extract and add metrics
uv run --env-file backend/keys.env extract_evaluation_results/step_5.py --arxiv_id "2406.09414"
```

The script will:
1. Read step_1 output (evaluation results) from cache
2. Extract all unique metric names from evaluation results
3. Query database for existing metrics
4. Identify missing metrics and determine their direction
5. Add missing metrics to the database
6. Return summary of found and added metrics
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
from extract_evaluation_results.tools import get_existing_metrics, add_metric

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Step5Input(BaseModel):
    """Input data for Step5."""

    arxiv_id: str
    evaluation_results: list[dict[str, Any]]


class Step5Output(BaseModel):
    """Output data for Step5."""

    metrics_found: list[dict[str, Any]]  # Metrics already in DB
    metrics_added: list[dict[str, Any]]  # Newly added metrics
    total_unique_metrics: int
    all_metrics: dict[str, str]  # name -> direction mapping


metrics_manager_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.

## Task

You are an expert in managing evaluation metrics in a SQL database. Your responsibility is to extract metric names from evaluation results and ensure all metrics exist in the database with correct directions (higher_is_better or lower_is_better).

A colleague has extracted evaluation results from a paper (Step 1), and now you need to:
1. Extract all unique metric names from the evaluation results
2. Check which metrics already exist in the database
3. Identify missing metrics
4. Determine the correct direction for each missing metric
5. Add missing metrics to the database

## Understanding Metric Directions

Metrics have two types of directions:

### Higher is Better (higher_is_better)
Metrics where higher values indicate better performance:
- **Accuracy** measures: Accuracy, Top-1 Accuracy, Top-5 Accuracy, Precision, Recall, F1, F-Score
- **Detection metrics**: AP, mAP, Average Precision, Mean Average Precision, AP50, AP75, APs, APm, APl
- **Segmentation**: IoU, Intersection over Union, Dice, Mask AP
- **Translation/Generation**: BLEU, ROUGE, ROUGE-L, ROUGE-1, ROUGE-2, METEOR, CIDEr
- **Ranking**: AUC, Area Under Curve, NDCG, Mean Reciprocal Rank, MRR
- **Scores**: Score, Accuracy Score, Exact Match (EM), Correlation

### Lower is Better (lower_is_better)
Metrics where lower values indicate better performance:
- **Error rates**: Error, Error Rate, Top-1 Error, Top-5 Error, WER (Word Error Rate), CER (Character Error Rate)
- **Loss**: Loss, Cross Entropy, BCE, MSE, MAE, RMSE
- **Distance**: Distance, L1, L2, Euclidean Distance
- **Time/Efficiency**: Latency, Inference Time, FLOPs, Parameters, Memory
- **Perplexity**: Perplexity, PPL

## Metric Name Normalization

When adding metrics, use standard naming conventions:
- Use common abbreviations: "WER" not "Word Error Rate" as the name
- Keep consistent casing: "AP", "mAP", "BLEU", "ROUGE-L"
- Full name goes in the `full_name` field
- For compound metrics like "AP50", if it's a variation of AP, still mark it as higher_is_better

## Pattern-Based Direction Detection

Use these patterns to determine direction:

**Lower is better if name contains:**
- "error", "loss", "perplexity", "latency", "time"
- Specifically "WER", "CER", "rate" (in context of error)

**Higher is better if name contains:**
- "accuracy", "precision", "recall", "f1", "f-score"
- "ap" (average precision), "auc", "iou", "dice"
- "bleu", "rouge", "meteor", "cider"
- "score", "match" (exact match)

**Default**: If uncertain, default to "higher_is_better" and add a note in the description.

## Tools Available

### get_existing_metrics()
Call this tool to retrieve all metrics currently in the database with their names, directions, and descriptions.

### add_metric(name, full_name, direction, description)
Call this tool to add a new metric to the database.

Args:
- name: Short metric name (e.g., "WER", "AP", "F1")
- full_name: Full descriptive name (e.g., "Word Error Rate")
- direction: Either "higher_is_better" or "lower_is_better"
- description: Optional description of what the metric measures

## Workflow

1. First, call `get_existing_metrics()` to see what metrics are already in the database
2. Extract all unique metric names from the evaluation results provided
3. Compare extracted metrics against existing metrics (case-insensitive)
4. For each missing metric:
   a. Determine the correct direction based on patterns above
   b. Generate a full_name (expand abbreviations if known)
   c. Create a description (optional but helpful)
   d. Call `add_metric()` to add it to the database
5. Return a summary in the Step5Output format

## Output Format

Return a Step5Output with:

```python
class Step5Output(BaseModel):
    metrics_found: list[dict]  # Metrics that already existed
                               # Format: [{"name": "AP", "direction": "higher_is_better"}, ...]
    metrics_added: list[dict]  # Metrics that were added
                               # Format: [{"name": "WER", "direction": "lower_is_better"}, ...]
    total_unique_metrics: int  # Total number of unique metrics in evaluation results
    all_metrics: dict[str, str]  # Complete mapping: name -> direction
                                 # Format: {"AP": "higher_is_better", "WER": "lower_is_better"}
```

## Important Notes

1. **Case-insensitive matching**: "ap" should match "AP" in the database
2. **Be comprehensive**: Extract ALL metric names from ALL evaluation results
3. **Avoid duplicates**: Don't try to add metrics that already exist
4. **Consistent naming**: Use standard abbreviations for metric names
5. **Document uncertainty**: If unsure about direction, add a note in description

Process ALL metrics found in the evaluation results. Your output will be used by subsequent steps to validate and normalize evaluation results before adding them to the database.
"""


class Step5(AgentStep[Step5Input, Step5Output]):
    """Agent-based metrics extraction and management."""

    input_model = Step5Input
    output_model = Step5Output

    def __init__(self):
        super().__init__(
            name="Step5: Metrics Manager",
            description="Extracts metrics from evaluation results and manages them in the database",
            instructions=metrics_manager_prompt,
            tools=[get_existing_metrics, add_metric],
            model="gpt-5-mini",
            agent_output_type=AgentOutputSchema(Step5Output, strict_json_schema=False),
        )

    async def build_agent_prompt(self, inputs: Step5Input) -> str:
        """Convert Step5Input to agent input prompt with context."""
        logger.info(
            f"Building prompt for {len(inputs.evaluation_results)} evaluation results"
        )

        # Format evaluation results
        eval_text = "### Evaluation Results with Metrics\n\n"
        eval_text += f"Paper ArXiv ID: {inputs.arxiv_id}\n"
        eval_text += f"Total evaluation results: {len(inputs.evaluation_results)}\n\n"

        # Show metrics in context
        eval_text += "Below are the evaluation results. Extract all unique metric names from the 'metrics' fields:\n\n"
        eval_text += "```json\n"
        eval_text += json.dumps(inputs.evaluation_results, indent=2)
        eval_text += "\n```\n"

        # Construct full prompt
        prompt = f"""
{eval_text}

## Your Task

Process the {len(inputs.evaluation_results)} evaluation results above:

1. **Call get_existing_metrics()** to see what metrics are already in the database
2. **Extract all unique metric names** from the evaluation results' 'metrics' fields
   - Each evaluation result has a 'metrics' dict like {{"AP": "44.9", "AP50": "64.7"}}
   - Extract all keys from all metrics dicts
3. **Compare extracted metrics against existing metrics** (case-insensitive comparison)
4. **For each missing metric:**
   - Determine direction using the patterns described in the instructions
   - Generate a full_name (expand abbreviations if you know them)
   - Create a helpful description (optional)
   - Call add_metric() to add it to the database
5. **Return Step5Output** with:
   - metrics_found: List of metrics that already existed
   - metrics_added: List of metrics that were newly added
   - total_unique_metrics: Total count of unique metrics found
   - all_metrics: Complete mapping of metric name -> direction

Process every unique metric. Don't skip any.
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


async def step_5(
    arxiv_id: str,
    evaluation_results: list,
) -> Optional[Step5Output]:
    """
    Extract and manage metrics from evaluation results (wrapper for Step5).

    Args:
        arxiv_id: The ArXiv ID of the paper
        evaluation_results: List of evaluation results from step_1

    Returns:
        Step5Output with metrics summary, or None if failed
    """
    agent = Step5()
    input_data = Step5Input(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
    )
    result = await agent.run(input_data)

    if not result.success:
        print(f"Step 5 failed: {result.error_message}")
        return None

    return result.outputs


async def main():
    parser = argparse.ArgumentParser(
        description="Extract and manage metrics from evaluation results using AI agent."
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
        return {
            "metrics_found": [],
            "metrics_added": [],
            "total_unique_metrics": 0,
            "all_metrics": {},
        }

    # Run metrics management
    result = await step_5(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
    )

    if not result:
        print("Metrics management failed")
        return None

    # Write output
    output_dir = get_output_dir(arxiv_id)
    output_path = output_dir / "step_5_metrics.json"
    output_path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    )
    print(f"✓ Metrics summary written to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("METRICS SUMMARY")
    print("=" * 60)
    print(f"Total unique metrics found: {result.total_unique_metrics}")
    print(f"Metrics already in database: {len(result.metrics_found)}")
    print(f"Metrics newly added: {len(result.metrics_added)}")

    if result.metrics_found:
        print("\n✓ Metrics found in database:")
        for metric in result.metrics_found:
            print(f"  - {metric['name']} ({metric['direction']})")

    if result.metrics_added:
        print("\n✓ Metrics newly added:")
        for metric in result.metrics_added:
            print(f"  - {metric['name']} ({metric['direction']})")

    print("\n" + "All metrics mapping:")
    for name, direction in result.all_metrics.items():
        print(f"  {name}: {direction}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\n✓ Step 5 completed successfully")


# Workflow integration
class Step5WorkflowStep:
    """Workflow step wrapper for Step5."""

    name = "Step5WorkflowStep"

    def __init__(self):
        self.step = Step5()

    async def execute(self, state):
        """
        Execute Step5 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str
        - evaluation_results: list (from Step 1)

        Writes to state.data:
        - metrics_found: list - metrics already in database
        - metrics_added: list - newly added metrics
        - total_unique_metrics: int - total unique metrics count
        - all_metrics: dict - name -> direction mapping
        """
        # Build inputs from state.data
        evaluation_results = state.data.get("evaluation_results", [])

        # Early return if no evaluation results to process
        if not evaluation_results:
            logger.info("No evaluation results to process. Skipping Step 5.")
            empty_output = Step5Output(
                metrics_found=[],
                metrics_added=[],
                total_unique_metrics=0,
                all_metrics={},
            )
            return StepResult(
                success=True,
                outputs=empty_output,
            )

        inputs = {
            "arxiv_id": state.data.get("arxiv_id", state.arxiv_id),
            "evaluation_results": evaluation_results,
        }

        # Execute the agent step
        result = await self.step.run(inputs)

        return result
