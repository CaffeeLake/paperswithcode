"""
Add ImageNet datasets to database using step_4 with pre-gathered step_3 results.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path to import step modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_evaluation_results.step_4 import step_4


async def main():
    """Add datasets using step_4."""
    # Read step_3 results
    step_3_file = (
        Path(__file__).parent.parent
        / "backend"
        / "outputs"
        / "evaluation_results"
        / "imagenet_variants"
        / "step_3_results.json"
    )

    with open(step_3_file, "r") as f:
        step_3_results = json.load(f)

    print("=" * 80)
    print("Adding ImageNet Datasets to Database (Step 4)")
    print("=" * 80)
    print()

    # Build dataset details for step_4
    datasets_to_add = []
    for result in step_3_results:
        if not result.get("success") or not result.get("information"):
            continue

        info = result["information"]
        dataset_input = result.get("dataset_input", {})

        # Extract task_id from step_3 output (required field)
        task_id = info.get("task_id")
        if task_id is None:
            print(
                f"⚠ Missing task_id for {dataset_input.get('dataset_name', 'Unknown')}, skipping"
            )
            continue

        # Build dataset details for adding to database
        dataset_details = {
            "name": dataset_input.get("dataset_name", info.get("full_name", "Unknown")),
            "description": info.get("description", ""),
            "full_name": info.get("full_name"),
            "hf_url": info.get("hf_url"),
            "paper_url": info.get("conference_url"),
            "paper_arxiv_id": info.get("arxiv_id"),
            "task_ids": [task_id],  # Use task_id from step_3
        }
        datasets_to_add.append(dataset_details)

    if not datasets_to_add:
        print("✗ No datasets to add.")
        return False

    print(f"Preparing to add {len(datasets_to_add)} datasets to database...")
    for idx, dataset in enumerate(datasets_to_add, 1):
        print(
            f"  {idx}. {dataset.get('name', 'Unknown')} (Task ID: {dataset.get('task_ids', [])[0]})"
        )
    print()

    # Add datasets to database one at a time to avoid cancellation issues
    print("Adding datasets sequentially to avoid async issues...")
    print("-" * 80)

    all_results = []
    for idx, dataset in enumerate(datasets_to_add, 1):
        print(
            f"\n[{idx}/{len(datasets_to_add)}] Adding {dataset.get('name', 'Unknown')}..."
        )
        try:
            results = await step_4([dataset])
            all_results.extend(results)
            if results and results[0].get("success"):
                details = results[0].get("dataset_details", {})
                print(
                    f"✓ Successfully added: {details.get('name', 'N/A')} (ID: {details.get('id', 'N/A')})"
                )
            else:
                error = (
                    results[0].get("error_message", "Unknown error")
                    if results
                    else "No result"
                )
                print(f"✗ Failed: {error}")
        except Exception as e:
            print(f"✗ Exception: {e}")
            all_results.append(
                {
                    "dataset_input": dataset,
                    "success": False,
                    "dataset_details": None,
                    "error_message": str(e),
                }
            )

    # Display summary
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY:")
    print("=" * 80)
    success_count = sum(1 for r in all_results if r.get("success"))
    print(
        f"Successfully added {success_count}/{len(all_results)} datasets to database\n"
    )

    for idx, result in enumerate(all_results, 1):
        dataset_name = result.get("dataset_input", {}).get("name", "Unknown")
        status = "✓" if result.get("success") else "✗"
        print(f"{idx}. {status} {dataset_name}")
        if result.get("success") and result.get("dataset_details"):
            details = result["dataset_details"]
            print(
                f"   → Added as: {details.get('name', 'N/A')} (ID: {details.get('id', 'N/A')}, Slug: {details.get('slug', 'N/A')})"
            )
        elif result.get("error_message"):
            print(f"   Error: {result['error_message']}")
        print()

    print("=" * 80)

    # Save results
    output_dir = (
        Path(__file__).parent.parent
        / "backend"
        / "outputs"
        / "evaluation_results"
        / "imagenet_variants"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    step_4_file = output_dir / "step_4_results.json"
    step_4_file.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"✓ Step 4 results saved to: {step_4_file}")

    return success_count == len(all_results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
