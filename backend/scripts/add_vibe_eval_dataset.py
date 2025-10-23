#!/usr/bin/env python3
"""
Add Vibe-Eval dataset to the database via the FastAPI backend.

This script:
1. Finds the Vision Language Models task ID
2. Creates the Vibe-Eval dataset
3. Links it to the Vision Language Models task
"""

import requests
import sys
import os
from typing import Optional

# API base URL
API_BASE_URL = os.getenv("PWC_API_URL", "http://localhost:8000/api/v1")


def find_vision_language_models_task() -> Optional[int]:
    """
    Find the Vision-Language Models task ID.

    Returns:
        Task ID if found, None otherwise
    """
    print("=" * 80)
    print("Step 1: Finding Vision-Language Models task...")
    print("=" * 80)

    try:
        # Try to get the task directly by slug first
        print("  Trying to get task by slug: vision-language-models")
        response = requests.get(f"{API_BASE_URL}/tasks/vision-language-models")

        if response.status_code == 200:
            task = response.json()
            task_id = int(task["id"])
            print(f"✓ Found task: {task['name']}")
            print(f"  ID: {task_id}")
            print(f"  Slug: {task.get('slug', 'N/A')}")
            print(f"  Description: {task.get('description', 'N/A')[:100]}...")
            return task_id

        # If slug doesn't work, try listing all tasks and finding it
        print("  Slug not found, searching through all tasks...")
        response = requests.get(f"{API_BASE_URL}/tasks/", params={"page_size": 100})
        response.raise_for_status()
        data = response.json()

        # Look for exact match (try both variations)
        for task in data.get("results", []):
            if task["name"] in ["Vision-Language Models", "Vision Language Models"]:
                task_id = int(task["id"])
                print(f"✓ Found task: {task['name']}")
                print(f"  ID: {task_id}")
                print(f"  Slug: {task.get('slug', 'N/A')}")
                print(f"  Description: {task.get('description', 'N/A')[:100]}...")
                return task_id

        print("✗ Vision-Language Models task not found")
        print(f"  Tasks checked: {len(data.get('results', []))}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"✗ Error searching for task: {e}")
        return None


def create_vibe_eval_dataset(task_id: int) -> Optional[dict]:
    """
    Create the Vibe-Eval dataset via API.

    Args:
        task_id: The Vision Language Models task ID

    Returns:
        Created dataset object if successful, None otherwise
    """
    print("\n" + "=" * 80)
    print("Step 2: Creating Vibe-Eval dataset...")
    print("=" * 80)

    # Dataset information from the paper
    dataset_data = {
        "name": "Vibe-Eval",
        "full_name": "Vibe-Eval: A hard evaluation suite for measuring progress of multimodal language models",
        "description": (
            "Vibe-Eval is an open benchmark for evaluating multimodal chat models. "
            "It consists of 269 visual understanding prompts, including 100 of hard difficulty, "
            "complete with gold-standard responses authored by experts. The benchmark is designed "
            "to be open-ended and challenging with dual objectives: (i) vibe checking multimodal "
            "chat models for day-to-day tasks and (ii) rigorously testing and probing the capabilities "
            "of present frontier models. Notably, the hard set contains >50% questions that all "
            "frontier models answer incorrectly."
        ),
        "url": "https://reka.ai/news/vibe-eval",
        "paper_url": "https://arxiv.org/abs/2405.02287",
        "task_ids": [task_id],
        "modalities": ["Images", "Text"],
        "languages": ["English"],
        "introduced_date": "2024-05-03",
    }

    print("Dataset details:")
    print(f"  Name: {dataset_data['name']}")
    print(f"  Full Name: {dataset_data['full_name']}")
    print(f"  URL: {dataset_data['url']}")
    print(f"  Paper: {dataset_data['paper_url']}")
    print(f"  Task IDs: {dataset_data['task_ids']}")
    print(f"  Modalities: {dataset_data['modalities']}")
    print(f"  Languages: {dataset_data['languages']}")
    print(f"  Introduced: {dataset_data['introduced_date']}")

    try:
        response = requests.post(f"{API_BASE_URL}/datasets/", json=dataset_data)
        response.raise_for_status()
        dataset = response.json()

        print("\n✓ Successfully created dataset!")
        print(f"  Dataset ID: {dataset.get('id')}")
        print(f"  Slug: {dataset.get('slug')}")
        print(f"  Name: {dataset.get('name')}")

        return dataset

    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP Error creating dataset: {e}")
        if e.response is not None:
            print(f"  Status code: {e.response.status_code}")
            print(f"  Response: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"✗ Error creating dataset: {e}")
        return None


def verify_dataset(dataset_id: str) -> bool:
    """
    Verify the dataset was created and linked correctly.

    Args:
        dataset_id: The dataset ID to verify

    Returns:
        True if verification successful, False otherwise
    """
    print("\n" + "=" * 80)
    print("Step 3: Verifying dataset creation...")
    print("=" * 80)

    try:
        # Get the dataset
        response = requests.get(f"{API_BASE_URL}/datasets/{dataset_id}")
        response.raise_for_status()
        dataset = response.json()

        print("✓ Dataset retrieved successfully!")
        print(f"  ID: {dataset.get('id')}")
        print(f"  Name: {dataset.get('name')}")
        print(f"  Slug: {dataset.get('slug')}")
        print(f"  URL: {dataset.get('url')}")
        print(f"  Paper URL: {dataset.get('paper_url')}")
        print(f"  Task Count: {dataset.get('task_count', 'N/A')}")

        return True

    except requests.exceptions.RequestException as e:
        print(f"✗ Error verifying dataset: {e}")
        return False


def main():
    """Main execution function."""
    print("\n🚀 Adding Vibe-Eval Dataset via API")
    print("=" * 80)
    print(f"API URL: {API_BASE_URL}")
    print("=" * 80)

    # Step 1: Find the Vision-Language Models task
    task_id = find_vision_language_models_task()
    if not task_id:
        print("\n❌ Failed to find Vision-Language Models task")
        print("   Please ensure:")
        print("   1. The API server is running")
        print("   2. The Vision-Language Models task exists in the database")
        sys.exit(1)

    # Step 2: Create the Vibe-Eval dataset
    dataset = create_vibe_eval_dataset(task_id)
    if not dataset:
        print("\n❌ Failed to create Vibe-Eval dataset")
        print("   Check the error messages above for details")
        sys.exit(1)

    # Step 3: Verify the dataset
    dataset_id = dataset.get("id")
    if dataset_id:
        verified = verify_dataset(dataset_id)
        if not verified:
            print("\n⚠️ Dataset created but verification failed")
            sys.exit(1)

    # Success!
    print("\n" + "=" * 80)
    print("✅ SUCCESS!")
    print("=" * 80)
    print("Vibe-Eval dataset has been successfully added to the database!")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Dataset Slug: {dataset.get('slug')}")
    print(f"  Linked to task: Vision-Language Models (ID: {task_id})")
    print("\nYou can view the dataset at:")
    print(f"  API: {API_BASE_URL}/datasets/{dataset_id}")
    print(f"  Or: {API_BASE_URL}/datasets/{dataset.get('slug')}")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
