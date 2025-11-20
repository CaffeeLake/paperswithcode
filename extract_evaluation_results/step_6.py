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
import subprocess
import sys
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


class MetricInfo(BaseModel):
    """Metric information with direction and scale."""

    direction: str
    scale: Optional[str] = None


class Step6Input(BaseModel):
    """Input data for Step6."""

    arxiv_id: str
    evaluation_results: list[dict[str, Any]]
    step_2_results: list[dict[str, Any]]
    step_4_results: Optional[list[dict[str, Any]]] = None
    step_5_all_metrics: Optional[dict[str, MetricInfo]] = (
        None  # Metric name -> {"direction": ..., "scale": ...} mapping
    )


class Step6Output(BaseModel):
    """Output data for Step6."""

    normalized: list[dict[str, Any]]
    mapped: int
    unresolved: int
    dataset_mapping: dict[str, dict[str, Any]]


normalizer_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI), greatly inspired by the PapersWithCode project.
This way, people can track progress of state-of-the-art models over time.

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
3. Normalizing metric VALUES to match the canonical scale from the database
4. Ensuring paper_id and task_id are populated
5. Marking unresolvable evaluations with _unresolved flag

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
- `task_id`: Intelligently select the appropriate task_id from step_2_results based on context:
  **CRITICAL**: Datasets can support multiple tasks (e.g., COCO/LVIS for both Object Detection and Instance Segmentation).
  Look at the evaluation context to determine the correct task:
  - If metrics are bbox-focused (AP, AP50, mAP for boxes) → likely Object Detection (task_id=2)
  - If metrics are mask-focused (Mask AP, Mask mAP) → likely Instance Segmentation (task_id=3)
  - If only one task_id is available in dataset.task_ids, use that one
  - If multiple task_ids are available, analyze the metrics and model name to select the most appropriate one
  - Use metrics_by_task to see which task allows which metrics for the dataset

## Metric Normalization

Metrics often have synonyms or variations. Normalize them to canonical names used in existing evaluations.

Additionally, metric VALUES must be normalized to match the canonical scale stored in the database.

### Common Metric Synonyms

Learn these standard mappings:

**Object Detection / Instance Segmentation:**
- **CRITICAL**: "AP" / "Average Precision" / "Box AP" / "Object AP" → **ALWAYS "mAP"**
  - For Object Detection (task_id=2), "AP" in papers means mean Average Precision
  - This applies to ALL object detection datasets, even new ones without existing conventions
  - Only exception: specific variants like AP50, AP75, APs, APm, APl (keep these as-is)
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

### Metric Value Scale Normalization

**CRITICAL**: After Step 5, each metric has a canonical scale in the database (from step_5_all_metrics).
You MUST normalize metric values to match this canonical scale.

#### Scale Conversion Rules:

**From 0-100 to 0-1** (when database scale is "0-1" but paper uses percentage):
- If metric scale is "0-1" and value > 1.0, divide by 100
- Example: AbsRel = 4.3 (paper) → 0.043 (database, scale "0-1")
- Example: delta1 = 98.5 (paper) → 0.985 (database, scale "0-1")

**From 0-1 to 0-100** (when database scale is "0-100" but paper uses decimal):
- If metric scale is "0-100" and value < 1.0, multiply by 100
- Example: mIoU = 0.63 (paper) → 63.0 (database, scale "0-100")
- Example: Top-1 Accuracy = 0.884 (paper) → 88.4 (database, scale "0-100")

**No conversion needed** (when scales match):
- If metric scale is "0-100" and value is 85.3 → keep 85.3
- If metric scale is "0-1" and value is 0.043 → keep 0.043
- If metric scale is "unbounded" → keep as-is (no fixed range)

#### How to Apply Scale Normalization:

1. **Get metric info from step_5_all_metrics**: For each metric name, find its direction and scale
2. **Check current value**: Is the value in the correct scale?
3. **Convert if needed**:
   - Metric scale "0-1" + value > 1.0 → divide by 100
   - Metric scale "0-100" + value < 1.0 → multiply by 100
   - Otherwise keep as-is
4. **Update metrics dict**: Replace old values with normalized values

#### Important Notes:

- **Preserve precision**: When converting, keep reasonable precision (e.g., 0.043 not 0.043000000)
- **Apply to ALL metrics**: Check and convert every metric in the metrics dict, not just best_metric
- **String format**: Metric values are strings in the database, so "0.043" not 0.043
- **Document conversion**: If you convert a value, you can add a note like "_scale_converted": true

#### Examples:

**Example 1: Depth Estimation (AbsRel)**
```
Paper: {"AbsRel": "4.3"}
Database scale for AbsRel: "0-1"
Normalized: {"AbsRel": "0.043"}  (4.3 / 100 = 0.043)
```

**Example 2: Semantic Segmentation (mIoU)**
```
Paper: {"mIoU": "63.0"}
Database scale for mIoU: "0-100"
Normalized: {"mIoU": "63.0"}  (no conversion, already correct scale)
```

**Example 3: Mixed scales in one evaluation**
```
Paper: {"AbsRel": "4.3", "delta1": "98.5", "RMSE": "0.123"}
Database scales: AbsRel="0-1", delta1="0-1", RMSE="0-1"
Normalized: {"AbsRel": "0.043", "delta1": "0.985", "RMSE": "0.123"}
(First two converted, last one already correct)
```

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
2. **task_id** (int): Database ID of the task (intelligently selected from available dataset.task_ids based on evaluation context - see Dataset Normalization section)
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
6. **Related metrics consolidation**: If a paper reports multiple related metrics for the same dataset (e.g., "MME-P" and "MME-S" for the MME dataset), create separate evaluation entries for each. These will be automatically consolidated into a single evaluation with multiple metrics in post-processing.

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
            step_5_text += "The following metrics are now available in the database with their directions and scales:\n\n"
            step_5_text += "```json\n"
            # Convert MetricInfo objects to dicts for JSON serialization
            metrics_dict = {
                name: metric.model_dump() if hasattr(metric, "model_dump") else metric
                for name, metric in inputs.step_5_all_metrics.items()
            }
            step_5_text += json.dumps(metrics_dict, indent=2)
            step_5_text += "\n```\n"
            step_5_text += "\nUse these metric names, directions, and scales when normalizing evaluation results.\n"
            step_5_text += "IMPORTANT: Normalize metric VALUES to match the canonical scale shown above.\n"
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
2. **Metric Name Normalization**: Normalize metric names using common synonyms and existing leaderboard conventions
   - Use get_leaderboard_metrics(task_id, dataset_id) to check what metrics are used
   - For Object Detection tasks, ALWAYS convert "AP" to "mAP" (even for new datasets)
3. **Metric Value Normalization**: Normalize metric VALUES to match the canonical scale from step_5
   - Use step_5_all_metrics to get the scale for each metric
   - Convert values if needed (e.g., 4.3 → 0.043 for AbsRel with scale "0-1")
   - Apply to ALL metrics in the metrics dict
4. **Field Population**: Ensure paper_id ({"available: " + str(paper_id) if paper_id else "NOT FOUND"}), task_id, dataset_id, dataset_name are set
5. **Error Handling**: Mark unresolvable evaluations with _unresolved: true

Return a Step6Output with:
- `normalized`: List of all normalized evaluation results (including unresolved ones)
- `mapped`: Count of successfully normalized evaluations
- `unresolved`: Count of evaluations that couldn't be fully normalized
- `dataset_mapping`: Dictionary from original dataset names to {{id, canonical_name}}

Process every evaluation result. Do not skip any.
"""

        return prompt


def normalize_model_name(model_name: str) -> str:
    """Normalize model name for grouping (lowercase, strip whitespace)."""
    if not model_name:
        return ""
    return model_name.strip().lower()


def should_consolidate_models(name1: str, name2: str) -> bool:
    """Check if two model names should be consolidated."""
    norm1 = normalize_model_name(name1)
    norm2 = normalize_model_name(name2)

    # If normalized names are identical, consolidate
    if norm1 == norm2:
        return True

    # Use fuzzy matching for minor differences (e.g., typos, punctuation)
    from difflib import SequenceMatcher

    similarity = SequenceMatcher(None, norm1, norm2).ratio()

    # High threshold (0.95) to only consolidate very similar names
    return similarity >= 0.95


def consolidate_evaluations(normalized_evals: list[dict]) -> list[dict]:
    """
    Consolidate evaluations with same (paper_id, task_id, dataset_id, model_name)
    by merging their metrics into a single evaluation.

    Args:
        normalized_evals: List of normalized evaluation dictionaries

    Returns:
        List of consolidated evaluations with merged metrics
    """
    # Group by (paper_id, task_id, dataset_id, normalized_model_name)
    groups = {}

    for eval_result in normalized_evals:
        # Skip unresolved evaluations
        if eval_result.get("_unresolved"):
            continue

        key = (
            eval_result.get("paper_id"),
            eval_result.get("task_id"),
            eval_result.get("dataset_id"),
            normalize_model_name(eval_result.get("model_name", "")),
        )

        if key not in groups:
            groups[key] = []
        groups[key].append(eval_result)

    # Consolidate each group
    consolidated = []

    for (paper_id, task_id, dataset_id, _), evals in groups.items():
        if len(evals) == 1:
            # No consolidation needed
            consolidated.append(evals[0])
            continue

        # Merge metrics from all evaluations in the group
        merged_metrics = {}
        original_names = []

        for eval_result in evals:
            metrics = eval_result.get("metrics", {})
            merged_metrics.update(metrics)

            if "_original_dataset_name" in eval_result:
                original_names.append(eval_result["_original_dataset_name"])

        # Use the first evaluation as the base
        base_eval = evals[0].copy()
        base_eval["metrics"] = merged_metrics

        # Keep the first best_metric or use a heuristic
        # (Could be enhanced to choose based on metric importance)

        # Add consolidation metadata
        base_eval["_consolidated_from"] = len(evals)
        base_eval["_original_dataset_names"] = original_names

        consolidated.append(base_eval)

    # Add back unresolved evaluations
    for eval_result in normalized_evals:
        if eval_result.get("_unresolved"):
            consolidated.append(eval_result)

    return consolidated


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

    # Consolidate evaluations with same dataset
    consolidated = consolidate_evaluations(result.outputs.normalized)

    # Update the output with consolidated results
    result.outputs.normalized = consolidated
    result.outputs.mapped = len([e for e in consolidated if not e.get("_unresolved")])
    result.outputs.unresolved = len([e for e in consolidated if e.get("_unresolved")])

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
    step_2_path = output_dir / "step_2.json"
    if not step_2_path.exists():
        print(f"Warning: step_2 output not found at {step_2_path}")
        step_2_results = []
    else:
        step_2_data = json.loads(step_2_path.read_text())
        step_2_results = step_2_data.get("step_2_results", [])

    # Read step_4 output (optional)
    step_4_path = output_dir / "step_4.json"
    if step_4_path.exists():
        step_4_data = json.loads(step_4_path.read_text())
        if isinstance(step_4_data, dict):
            step_4_results = step_4_data.get("step_4_results", [])
        else:
            step_4_results = step_4_data
    else:
        step_4_results = []

    # Read step_5 output (optional)
    step_5_all_metrics = None
    step_5_candidates = [
        output_dir / "step_5_metrics.json",
        output_dir / "step_5.json",
    ]
    for step_5_path in step_5_candidates:
        if step_5_path.exists():
            step_5_data = json.loads(step_5_path.read_text())
            if isinstance(step_5_data, dict):
                step_5_all_metrics = step_5_data.get("all_metrics")
            break

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
        dataset_id = mapping.get("dataset_id") or mapping.get("id")
        print(
            f"  - '{original_name}' -> '{mapping['canonical_name']}' (ID: {dataset_id})"
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
        self.project_root = Path(__file__).resolve().parents[1]

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

        arxiv_id = state.data.get("arxiv_id", state.arxiv_id)

        cmd = [
            sys.executable,
            "extract_evaluation_results/step_6.py",
            "--arxiv_id",
            arxiv_id,
        ]

        try:
            subprocess.run(cmd, check=True, cwd=self.project_root)
        except subprocess.CalledProcessError as exc:
            logger.error("Step 6 subprocess failed: %s", exc)
            return StepResult(
                success=False,
                outputs=None,
                error_message=f"Step 6 subprocess failed with exit code {exc.returncode}",
            )

        output_dir = get_output_dir(arxiv_id)
        output_path = output_dir / "step_6_normalized.json"

        if output_path.exists():
            try:
                step6_data = json.loads(output_path.read_text())
                output = Step6Output.model_validate(step6_data)
            except Exception as exc:
                logger.error("Failed to parse Step 6 output: %s", exc)
                return StepResult(
                    success=False,
                    outputs=None,
                    error_message=f"Failed to parse Step 6 output: {exc}",
                )
        else:
            logger.warning(
                "Step 6 output file not found at %s, returning empty result",
                output_path,
            )
            output = Step6Output(
                normalized=[], mapped=0, unresolved=0, dataset_mapping={}
            )

        return StepResult(success=True, outputs=output)
