"""
Add ImageNet variant datasets to the database using step_3 and step_4.

This script adds the following ImageNet datasets:
- ImageNet V2
- ImageNet-R
- ImageNet-S
- ImageNet-Hard

It uses the step_3 agent to gather information about each dataset,
then uses step_4 agent to add them to the database.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path to import step modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_evaluation_results.step_3 import step_3
from extract_evaluation_results.step_4 import step_4


# Define the ImageNet variant datasets to add
IMAGENET_DATASETS = [
    {
        "dataset_name": "ImageNet V2",
        "dataset_info": "ImageNet V2 is a test set for ImageNet classification that was collected to match the original ImageNet validation set distribution.",
    },
    {
        "dataset_name": "ImageNet-R",
        "dataset_info": "ImageNet-R (ImageNet-Rendition) is a dataset of renditions of ImageNet classes, including art, cartoons, deviantart, graffiti, embroidery, graphics, origami, paintings, patterns, plastic objects, plush objects, sculptures, sketches, tattoos, toys, and video game renditions.",
    },
    {
        "dataset_name": "ImageNet-S",
        "dataset_info": "ImageNet-S (ImageNet-Sketch) is a dataset of sketch images matching ImageNet classes.",
    },
    {
        "dataset_name": "ImageNet-Hard",
        "dataset_info": "ImageNet-Hard is a challenging subset of ImageNet with harder examples for robustness evaluation.",
    },
]


async def main():
    """Main function to add ImageNet datasets."""
    print("=" * 80)
    print("Adding ImageNet Variant Datasets to Database")
    print("=" * 80)
    print()

    # Step 1: Gather information about each dataset using step_3
    print("Step 1: Gathering information about datasets using step_3...")
    print("-" * 80)

    step_3_results = await step_3(IMAGENET_DATASETS)

    # Check results
    success_count = sum(1 for r in step_3_results if r.get("success"))
    print(
        f"\n✓ Successfully gathered information for {success_count}/{len(step_3_results)} datasets\n"
    )

    # Display step_3 results
    for idx, result in enumerate(step_3_results, 1):
        dataset_name = result.get("dataset_input", {}).get("dataset_name", "Unknown")
        status = "✓" if result.get("success") else "✗"
        print(f"{idx}. {status} {dataset_name}")
        if result.get("success") and result.get("information"):
            info = result["information"]
            print(f"   Full name: {info.get('full_name', 'N/A')}")
            print(f"   Task ID: {info.get('task_id', 'N/A')}")
            if info.get("hf_url"):
                print(f"   HF URL: {info['hf_url']}")
            if info.get("arxiv_id"):
                print(f"   ArXiv ID: {info['arxiv_id']}")
        elif result.get("error_message"):
            print(f"   Error: {result['error_message']}")
        print()

    # Filter to only successfully gathered datasets
    successful_gathers = [
        r for r in step_3_results if r.get("success") and r.get("information")
    ]

    if not successful_gathers:
        print("✗ No datasets were successfully gathered. Cannot proceed to step_4.")
        return False

    # Step 2: Add datasets to database using step_4
    print("\n" + "=" * 80)
    print("Step 2: Adding datasets to database using step_4...")
    print("-" * 80)

    # Build dataset details for step_4
    datasets_to_add = []
    for result in successful_gathers:
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
        print("✗ No datasets to add (all missing task_id).")
        return False

    print(f"Preparing to add {len(datasets_to_add)} datasets to database...")
    for idx, dataset in enumerate(datasets_to_add, 1):
        print(
            f"  {idx}. {dataset.get('name', 'Unknown')} (Task ID: {dataset.get('task_ids', [])[0]})"
        )

    # Add datasets to database
    step_4_results = await step_4(datasets_to_add)

    # Display step_4 results
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY:")
    print("=" * 80)
    success_count = sum(1 for r in step_4_results if r.get("success"))
    print(
        f"Successfully added {success_count}/{len(step_4_results)} datasets to database\n"
    )

    for idx, result in enumerate(step_4_results, 1):
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

    # Save results to JSON files for reference
    output_dir = (
        Path(__file__).parent.parent
        / "backend"
        / "outputs"
        / "evaluation_results"
        / "imagenet_variants"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    step_3_file = output_dir / "step_3_results.json"
    step_3_file.write_text(json.dumps(step_3_results, indent=2, ensure_ascii=False))
    print(f"✓ Step 3 results saved to: {step_3_file}")

    step_4_file = output_dir / "step_4_results.json"
    step_4_file.write_text(json.dumps(step_4_results, indent=2, ensure_ascii=False))
    print(f"✓ Step 4 results saved to: {step_4_file}")

    return success_count == len(step_4_results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
