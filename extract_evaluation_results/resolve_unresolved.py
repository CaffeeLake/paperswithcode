"""
Script to resolve unresolved evaluation results by mapping datasets from step_2 and step_4.

This script reads step_2.json and step_4.json to create a mapping from original dataset names
to database IDs and task IDs, then updates step_6.json to resolve all unresolved evaluations.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any


def build_dataset_mapping(
    step_2_results: list, step_4_results: list
) -> Dict[str, Dict[str, Any]]:
    """
    Build a mapping from original dataset names to database information.

    Args:
        step_2_results: List of step 2 results (datasets found in database)
        step_4_results: List of step 4 results (datasets newly added)

    Returns:
        Dictionary mapping original dataset names to {id, canonical_name, task_ids}
    """
    mapping = {}

    # Process step_2 results (datasets found in database)
    for result in step_2_results:
        if result.get("success") and result.get("result", {}).get("found"):
            dataset_input = result.get("dataset", {}).get("dataset_name")
            dataset_info = result.get("result", {}).get("dataset", {})

            if dataset_input and dataset_info:
                mapping[dataset_input.lower()] = {
                    "id": dataset_info.get("id"),
                    "canonical_name": dataset_info.get("name"),
                    "task_ids": dataset_info.get("task_ids", []),
                }

    # Process step_4 results (datasets newly added)
    for result in step_4_results:
        if result.get("success"):
            dataset_input = result.get("dataset_input", {}).get("name")
            dataset_details = result.get("dataset_details", {})

            if dataset_input and dataset_details:
                mapping[dataset_input.lower()] = {
                    "id": dataset_details.get("id"),
                    "canonical_name": dataset_details.get("name"),
                    "task_ids": dataset_details.get("task_ids", []),
                }

    return mapping


def normalize_dataset_name(name: str) -> str:
    """Normalize dataset name for matching (lowercase, strip whitespace)."""
    return name.lower().strip()


def resolve_evaluation(
    eval_result: Dict[str, Any], mapping: Dict[str, Dict[str, Any]], paper_id: int
) -> Dict[str, Any]:
    """
    Resolve a single evaluation result using the dataset mapping.

    Args:
        eval_result: Evaluation result dictionary
        mapping: Dataset name to database info mapping
        paper_id: Paper ID from database

    Returns:
        Resolved evaluation result dictionary
    """
    original_name = eval_result.get("_original_dataset_name") or eval_result.get(
        "dataset_name"
    )

    if not original_name:
        return eval_result

    # Try exact match first
    normalized_name = normalize_dataset_name(original_name)
    dataset_info = mapping.get(normalized_name)

    # Try fuzzy matching for common variations
    if not dataset_info:
        # Remove parenthetical notes
        base_name = original_name.split("(")[0].strip()
        dataset_info = mapping.get(normalize_dataset_name(base_name))

    if not dataset_info:
        # Try removing "w/ audio" or similar suffixes
        base_name = original_name.split("(w/")[0].split("(w/ ")[0].strip()
        dataset_info = mapping.get(normalize_dataset_name(base_name))

    # Special case mappings based on step_2 reasoning
    if not dataset_info:
        special_mappings = {
            "mmbench-enest": "mmbench-en",
            "refcoco (averaged)": "refcoco",
            "videomme (w/ audio)": "video-mme",
            "librispeech test-clean": "librispeech clean",
            "covost2 (en→zh)": "covost2 (en→zh)",
            "openaudiobench - llamquestions": "openaudiobench - llamquestions",
        }
        mapped_name = special_mappings.get(normalized_name)
        if mapped_name:
            dataset_info = mapping.get(normalize_dataset_name(mapped_name))

    if dataset_info:
        # Resolve the evaluation
        eval_result["dataset_id"] = dataset_info["id"]
        eval_result["dataset_name"] = dataset_info["canonical_name"]
        eval_result["dataset_name_canonical"] = dataset_info["canonical_name"]
        eval_result["task_id"] = (
            dataset_info["task_ids"][0] if dataset_info["task_ids"] else None
        )
        eval_result["paper_id"] = paper_id
        eval_result["_unresolved"] = False
        eval_result["_mapping_source"] = "resolved_by_script"
        eval_result["_reason"] = (
            f"Mapped from '{original_name}' to '{dataset_info['canonical_name']}' (ID: {dataset_info['id']})"
        )
    else:
        # Keep as unresolved but update reason
        eval_result["_unresolved"] = True
        eval_result["_reason"] = (
            f"Dataset '{original_name}' not found in step_2 or step_4 results"
        )

    return eval_result


def resolve_step_6(arxiv_id: str) -> bool:
    """
    Resolve unresolved evaluations in step_6.json.

    Args:
        arxiv_id: ArXiv ID of the paper

    Returns:
        True if successful, False otherwise
    """
    output_dir = Path("backend/outputs/evaluation_results") / arxiv_id

    # Read step_2 results
    step_2_path = output_dir / "step_2.json"
    if not step_2_path.exists():
        print(f"Error: step_2.json not found at {step_2_path}")
        return False

    with open(step_2_path) as f:
        step_2_results = json.load(f)

    # Read step_4 results
    step_4_path = output_dir / "step_4.json"
    step_4_results = []
    if step_4_path.exists():
        with open(step_4_path) as f:
            step_4_results = json.load(f)

    # Build dataset mapping
    mapping = build_dataset_mapping(step_2_results, step_4_results)
    print(f"Built mapping for {len(mapping)} datasets")

    # Read step_6 results
    step_6_path = output_dir / "step_6.json"
    if not step_6_path.exists():
        print(f"Error: step_6.json not found at {step_6_path}")
        return False

    with open(step_6_path) as f:
        step_6_data = json.load(f)

    # Get paper_id from first evaluation (should be same for all)
    normalized = step_6_data.get("normalized", [])
    if not normalized:
        print("No normalized evaluations found in step_6.json")
        return False

    paper_id = normalized[0].get("paper_id")
    if not paper_id:
        print("Error: Could not determine paper_id from step_6.json")
        return False

    # Resolve each evaluation
    resolved_count = 0
    for eval_result in normalized:
        if eval_result.get("_unresolved"):
            before_unresolved = eval_result.get("_unresolved")
            resolved_eval = resolve_evaluation(eval_result, mapping, paper_id)
            if not resolved_eval.get("_unresolved") and before_unresolved:
                resolved_count += 1

    # Update counts
    step_6_data["mapped"] = sum(1 for e in normalized if not e.get("_unresolved"))
    step_6_data["unresolved"] = sum(1 for e in normalized if e.get("_unresolved"))

    # Build dataset_mapping for output
    dataset_mapping = {}
    for eval_result in normalized:
        if not eval_result.get("_unresolved") and eval_result.get(
            "_original_dataset_name"
        ):
            orig_name = eval_result.get("_original_dataset_name")
            dataset_mapping[orig_name] = {
                "id": eval_result.get("dataset_id"),
                "canonical_name": eval_result.get("dataset_name_canonical"),
            }
    step_6_data["dataset_mapping"] = dataset_mapping

    # Write updated step_6.json
    with open(step_6_path, "w") as f:
        json.dump(step_6_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Resolved {resolved_count} evaluation(s)")
    print(
        f"✓ Total mapped: {step_6_data['mapped']}, Unresolved: {step_6_data['unresolved']}"
    )
    print(f"✓ Updated {step_6_path}")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python resolve_unresolved.py <arxiv_id>")
        sys.exit(1)

    arxiv_id = sys.argv[1]
    success = resolve_step_6(arxiv_id)
    sys.exit(0 if success else 1)
