"""
Step 5: Normalize evaluation results datasets.

This script normalizes the dataset names in evaluation results extracted from a paper
by mapping them to canonical dataset names and IDs from the database based on the outputs
of Step 2 (datasets found in database) and Step 4 (datasets newly added to database).

You can run it like so:

```bash
# Process evaluation results from step_1 using step_2 and step_4 outputs
uv run --env-file backend/keys.env extract_evaluation_results/step_5.py --arxiv_id "2406.09414"
```

The script will:
1. Read step_1, step_2, and step_4 outputs from cache
2. Build a mapping from original dataset names to canonical DB dataset names and IDs
3. Normalize each evaluation result by replacing dataset names with canonical names
4. Return normalized evaluation results with statistics
"""

import argparse
import asyncio
import json
import logging
from typing import Optional

from pydantic import BaseModel

from extract_evaluation_results.step_2 import (
    get_output_dir,
    read_step_1_output,
)
from extract_evaluation_results.dataset_utils import (
    extract_dataset_id,
    parse_dataset_info,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Step5Input(BaseModel):
    """Input data for Step5Normalizer."""

    arxiv_id: str
    evaluation_results: list
    step_2_results: list
    step_4_results: Optional[list] = None


class Step5Output(BaseModel):
    """Output data for Step5Normalizer."""

    normalized: list
    mapped: int
    unresolved: int
    dataset_mapping: dict


# Helper function for Step5Normalizer
def _normalize_compute(input_data: Step5Input) -> dict:
    """Compute function for Step5Normalizer."""
    return normalize_evaluation_datasets(
        arxiv_id=input_data.arxiv_id,
        evaluation_results=input_data.evaluation_results,
        step_2_results=input_data.step_2_results,
        step_4_results=input_data.step_4_results,
    )


def normalize_evaluation_datasets(
    arxiv_id: str,
    evaluation_results: list[dict],
    step_2_results: list[dict],
    step_4_results: Optional[list[dict]] = None,
) -> dict:
    """Normalize dataset names in evaluation results using Step 2 and Step 4 outputs.

    Args:
        arxiv_id: The ArXiv ID of the paper
        evaluation_results: List of evaluation results from step_1
        step_2_results: List of step_2 results (datasets found in database)
        step_4_results: Optional list of step_4 results (datasets newly added to database)

    Returns:
        Dictionary with:
        - normalized: List of normalized evaluation results
        - mapped: Number of evaluations successfully mapped
        - unresolved: Number of evaluations that couldn't be mapped
        - dataset_mapping: Dictionary showing the mapping used
    """
    logger.info(f"Normalizing {len(evaluation_results)} evaluation results")

    # Build dataset_name -> {id, canonical_name} mapping
    dataset_mapping = {}

    # Add datasets from step_2 (already in database)
    for step_2_result in step_2_results:
        # Step 2 returns "found" key, not "success"
        if not step_2_result.get("found"):
            continue

        # Step 2 result already has the right structure for parse_dataset_info
        dataset_info = parse_dataset_info(step_2_result)
        if dataset_info and dataset_info.get("id"):
            original_name = step_2_result.get("dataset_input", {}).get(
                "dataset_name", ""
            )
            dataset_mapping[original_name.lower()] = {
                "id": dataset_info["id"],
                "canonical_name": dataset_info.get("name", original_name),
                "source": "step_2",
            }
            logger.info(
                f"Mapped '{original_name}' to ID {dataset_info['id']} (from step_2)"
            )

    # Add datasets from step_4 (newly added to database OR already existing)
    if step_4_results:
        for step_4_result in step_4_results:
            original_name = step_4_result.get("dataset_input", {}).get(
                "dataset_name", ""
            )
            result = step_4_result.get("dataset_details")

            # Check if result is structured Pydantic model (DatasetDetails)
            if isinstance(result, dict) and "id" in result:
                # Structured output from DatasetDetails.model_dump()
                dataset_id = result.get("id")
                canonical_name = result.get("name", original_name)

                # Process if successful OR if we have a dataset ID
                if step_4_result.get("success") or dataset_id:
                    # If already mapped from step_2, check for conflicts
                    if original_name.lower() in dataset_mapping:
                        existing_id = dataset_mapping[original_name.lower()]["id"]
                        if existing_id != dataset_id:
                            logger.warning(
                                f"Dataset '{original_name}' mapped to different IDs: "
                                f"step_2={existing_id}, step_4={dataset_id}. Using step_4."
                            )

                    source = (
                        "step_4_added"
                        if step_4_result.get("success")
                        else "step_4_existing"
                    )
                    dataset_mapping[original_name.lower()] = {
                        "id": dataset_id,
                        "canonical_name": canonical_name,
                        "source": source,
                    }
                    logger.info(
                        f"Mapped '{original_name}' to ID {dataset_id} (from step_4, {'newly added' if step_4_result.get('success') else 'already existed'})"
                    )
                continue

            # Fallback: string result (legacy format or error)
            result_text = str(result) if result else ""

            # Check if step_4 says dataset already exists (even if success=False)
            already_exists = (
                "already in the database" in result_text.lower()
                or "already present in the database" in result_text.lower()
                or "already exists in the database" in result_text.lower()
            )

            # Try to extract dataset ID first - if we can extract an ID, the dataset was created
            dataset_id = step_4_result.get("dataset_id") or extract_dataset_id(
                result_text
            )
            has_dataset_id = dataset_id is not None

            # Process if successful OR if it already exists OR if we can extract a dataset ID
            # (the ID extraction indicates the dataset was actually created, even if success flag is wrong)
            if (
                not step_4_result.get("success")
                and not already_exists
                and not has_dataset_id
            ):
                continue

            if dataset_id:
                # Try to parse full dataset info from result
                dataset_info = parse_dataset_info(result_text)
                canonical_name = (
                    dataset_info.get("name", original_name)
                    if dataset_info
                    else original_name
                )

                # If already mapped from step_2, check for conflicts
                if original_name.lower() in dataset_mapping:
                    existing_id = dataset_mapping[original_name.lower()]["id"]
                    if existing_id != dataset_id:
                        logger.warning(
                            f"Dataset '{original_name}' mapped to different IDs: "
                            f"step_2={existing_id}, step_4={dataset_id}. Using step_4."
                        )

                source = (
                    "step_4_added"
                    if (step_4_result.get("success") or has_dataset_id)
                    else "step_4_existing"
                )
                dataset_mapping[original_name.lower()] = {
                    "id": dataset_id,
                    "canonical_name": canonical_name,
                    "source": source,
                }
                logger.info(
                    f"Mapped '{original_name}' to ID {dataset_id} (from step_4, {'newly added' if step_4_result.get('success') else 'already existed'})"
                )
            elif already_exists:
                # Dataset exists but we couldn't extract ID - need to search database
                logger.warning(
                    f"Dataset '{original_name}' already exists per step_4 but couldn't extract ID. "
                    f"Searching database..."
                )
                # Try to find it in the database by name
                from backend.database.connection import db_manager
                from backend.models.database import Dataset as DBDataset

                session = db_manager.session_local()
                try:
                    # Try exact match first
                    dataset = (
                        session.query(DBDataset)
                        .filter(DBDataset.name.ilike(original_name))
                        .first()
                    )

                    if dataset:
                        dataset_mapping[original_name.lower()] = {
                            "id": dataset.id,
                            "canonical_name": dataset.name,
                            "source": "step_4_existing_searched",
                        }
                        logger.info(
                            f"Found '{original_name}' in database: ID {dataset.id}, Name '{dataset.name}'"
                        )
                    else:
                        logger.warning(
                            f"Could not find dataset '{original_name}' in database despite step_4 saying it exists"
                        )
                finally:
                    session.close()

    if not dataset_mapping:
        logger.warning("No dataset mappings found from step_2 or step_4")
        return {
            "normalized": [],
            "mapped": 0,
            "unresolved": len(evaluation_results),
            "dataset_mapping": {},
        }

    # Get paper_id from arxiv_id
    paper_id = None
    try:
        from backend.database.connection import db_manager
        from backend.models.database import Paper

        session = db_manager.session_local()
        try:
            paper = (
                session.query(Paper).filter(Paper.arxiv_id.like(f"{arxiv_id}%")).first()
            )

            if paper:
                paper_id = paper.id
                logger.info(f"Found paper_id {paper_id} for arxiv_id {arxiv_id}")
            else:
                logger.warning(
                    f"Could not find paper with arxiv_id {arxiv_id} in database"
                )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error looking up paper_id: {e}")

    # Normalize evaluation results
    normalized_results = []
    mapped_count = 0
    unresolved_count = 0

    for eval_result in evaluation_results:
        dataset_name = eval_result.get("dataset_name", "")
        if not dataset_name:
            logger.warning("Evaluation result missing dataset_name, skipping")
            unresolved_count += 1
            continue

        dataset_name_lower = dataset_name.lower()
        if dataset_name_lower in dataset_mapping:
            # Create normalized evaluation result
            normalized_eval = eval_result.copy()
            mapping = dataset_mapping[dataset_name_lower]
            normalized_eval["dataset_name"] = mapping["canonical_name"]
            normalized_eval["dataset_id"] = mapping["id"]
            normalized_eval["_original_dataset_name"] = dataset_name
            normalized_eval["_mapping_source"] = mapping["source"]

            # Add paper_id
            if paper_id:
                normalized_eval["paper_id"] = paper_id

            # Get task_id from dataset's tasks
            task_id = None
            try:
                from backend.database.connection import db_manager
                from backend.models.database import Dataset as DBDataset

                session = db_manager.session_local()
                try:
                    dataset = (
                        session.query(DBDataset)
                        .filter(DBDataset.id == mapping["id"])
                        .first()
                    )

                    if dataset and dataset.tasks:
                        # Use the first task associated with the dataset
                        task_id = dataset.tasks[0].id
                        logger.debug(
                            f"Found task_id {task_id} for dataset {dataset.name}"
                        )
                finally:
                    session.close()
            except Exception as e:
                logger.error(
                    f"Error looking up task_id for dataset {mapping['id']}: {e}"
                )

            if task_id:
                normalized_eval["task_id"] = task_id
            else:
                logger.warning(
                    f"Could not find task_id for dataset '{mapping['canonical_name']}'"
                )

            # Convert metric_name/metric_value to metrics dict + best_metric
            metric_name = normalized_eval.get("metric_name")
            metric_value = normalized_eval.get("metric_value")

            if metric_name and metric_value:
                # Create metrics dictionary
                normalized_eval["metrics"] = {metric_name: metric_value}
                normalized_eval["best_metric"] = metric_name
                logger.debug(f"Converted metric: {metric_name}={metric_value}")

            normalized_results.append(normalized_eval)
            mapped_count += 1
            logger.debug(
                f"Normalized '{dataset_name}' -> '{mapping['canonical_name']}' (ID: {mapping['id']})"
            )
        else:
            logger.warning(
                f"No mapping found for dataset '{dataset_name}', marking as unresolved"
            )
            # Keep the original evaluation but mark as unresolved
            unresolved_eval = eval_result.copy()
            unresolved_eval["_unresolved"] = True
            normalized_results.append(unresolved_eval)
            unresolved_count += 1

    logger.info(
        f"Normalization complete: {mapped_count} mapped, {unresolved_count} unresolved"
    )

    return {
        "normalized": normalized_results,
        "mapped": mapped_count,
        "unresolved": unresolved_count,
        "dataset_mapping": {
            name: {"id": info["id"], "canonical_name": info["canonical_name"]}
            for name, info in dataset_mapping.items()
        },
    }


async def step_5(
    arxiv_id: str,
    evaluation_results: list,
    step_2_results: list,
    step_4_results: Optional[list] = None,
) -> dict:
    """
    Normalize evaluation results datasets (wrapper for Step5Normalizer).

    Args:
        arxiv_id: The ArXiv ID of the paper
        evaluation_results: List of evaluation results from step_1
        step_2_results: List of step_2 results (datasets found in database)
        step_4_results: Optional list of step_4 results (datasets newly added to database)

    Returns:
        Dictionary with normalized results and statistics
    """
    # Step5 is a deterministic normalization function, so we call it directly
    return normalize_evaluation_datasets(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
        step_4_results=step_4_results,
    )


async def main():
    parser = argparse.ArgumentParser(
        description="Normalize evaluation results datasets using step_2 and step_4 outputs."
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

    # Normalize datasets
    result = normalize_evaluation_datasets(
        arxiv_id=arxiv_id,
        evaluation_results=evaluation_results,
        step_2_results=step_2_results,
        step_4_results=step_4_results,
    )

    # Write output
    output_path = output_dir / "step_5_normalized.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"✓ Normalized results written to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("NORMALIZATION SUMMARY")
    print("=" * 60)
    print(f"Total evaluation results: {len(evaluation_results)}")
    print(f"Successfully mapped: {result['mapped']}")
    print(f"Unresolved: {result['unresolved']}")
    print(f"\nDataset mappings used: {len(result['dataset_mapping'])}")
    for original_name, mapping in result["dataset_mapping"].items():
        print(
            f"  - '{original_name}' -> '{mapping['canonical_name']}' (ID: {mapping['id']})"
        )
    print("=" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\nNormalized evaluation results:")
        print(json.dumps(result["normalized"][:3], indent=2))  # Show first 3
        if len(result["normalized"]) > 3:
            print(f"... and {len(result['normalized']) - 3} more")


# Workflow integration
class Step5WorkflowStep:
    """Workflow step wrapper for Step5."""

    name = "Step5WorkflowStep"

    def __init__(self):
        from extract_evaluation_results.step_5 import Step5Input, Step5Output

        self.input_model = Step5Input
        self.output_model = Step5Output

    async def execute(self, state):
        """
        Execute Step5 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str
        - evaluation_results: list
        - step_2_results: list
        - step_4_results: list (optional)

        Writes to state.data:
        - normalized: list of normalized evaluation results
        - mapped: int - number of mapped evaluations
        - unresolved: int - number of unresolved evaluations
        - dataset_mapping: dict - mapping from original to canonical names
        - step_5_normalized: dict - complete normalization result
        """
        from extract_evaluation_results.step_base import StepResult

        # Build inputs from state.data
        inputs = {
            "arxiv_id": state.data.get("arxiv_id", state.arxiv_id),
            "evaluation_results": state.data.get("evaluation_results", []),
            "step_2_results": state.data.get("step_2_results", []),
            "step_4_results": state.data.get("step_4_results"),
        }

        # Execute normalization directly (not an agent step)
        try:
            result_dict = _normalize_compute(self.input_model(**inputs))

            # Create output model
            output = self.output_model(**result_dict)

            # Return as StepResult
            return StepResult(
                success=True,
                outputs=output,
                reasoning=f"Normalized {result_dict.get('mapped', 0)} evaluations, {result_dict.get('unresolved', 0)} unresolved",
            )
        except Exception as e:
            logger.error(f"Step5 failed: {e}", exc_info=True)
            return StepResult(success=False, error_message=str(e), outputs=None)
