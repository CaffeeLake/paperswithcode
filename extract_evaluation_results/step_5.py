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

from extract_evaluation_results.step_2 import (
    parse_dataset_info,
    extract_dataset_id,
    get_output_dir,
    read_step_1_output,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        if not step_2_result.get("success"):
            continue

        # Pass the result dict directly to parse_dataset_info (not as string)
        result = step_2_result.get("result", {})
        dataset_info = parse_dataset_info(result)
        if dataset_info and dataset_info.get("id"):
            original_name = step_2_result["dataset"].get("dataset_name", "")
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
            result_text = str(step_4_result.get("result", ""))
            original_name = step_4_result["dataset"].get("dataset_name", "")

            # Check if step_4 says dataset already exists (even if success=False)
            already_exists = (
                "already in the database" in result_text.lower()
                or "already present in the database" in result_text.lower()
                or "already exists in the database" in result_text.lower()
            )

            # Only process if successful OR if it already exists
            if not step_4_result.get("success") and not already_exists:
                continue

            dataset_id = extract_dataset_id(result_text)
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
