"""
Add audio classification datasets from CSV to the database using the API.

This script reads the Audio Classification datasets CSV and creates each dataset
via the POST /api/v1/datasets/ API endpoint.
"""

import csv
import requests
import sys
from typing import Optional

# API configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TASK_ID = 259  # Audio Classification task ID

# CSV file path
CSV_FILE = "data/Audio language model datasets - Audio classification.csv"


def clean_url(url: Optional[str]) -> Optional[str]:
    """Clean URL field - treat '/' as missing/empty."""
    if not url or url.strip() == "/" or url.strip() == "":
        return None
    return url.strip()


def clean_description(description: str) -> str:
    """Clean description - concatenate multi-line into single line."""
    # Replace newlines with spaces and clean up extra whitespace
    cleaned = " ".join(description.split())
    return cleaned.strip()


def create_dataset(dataset_data: dict) -> dict:
    """
    Create a dataset via the API.

    Args:
        dataset_data: Dictionary with dataset information

    Returns:
        API response as dictionary
    """
    url = f"{API_BASE_URL}/datasets/"

    # Prepare the request payload
    payload = {
        "name": dataset_data["Dataset"],
        "description": clean_description(dataset_data["Description"]),
        "task_ids": [TASK_ID],
    }

    # Add optional fields only if they have valid values
    main_url = clean_url(dataset_data.get("url"))
    hf_url = clean_url(dataset_data.get("hf_url"))
    paper_url = clean_url(dataset_data.get("paper_url"))

    # Use hf_url as fallback for url if url is missing
    if not main_url and hf_url:
        main_url = hf_url

    if main_url:
        payload["url"] = main_url
    if hf_url:
        payload["hf_url"] = hf_url
    if paper_url:
        payload["paper_url"] = paper_url

    # Make the POST request
    response = requests.post(url, json=payload)

    return {
        "status_code": response.status_code,
        "success": response.status_code in [200, 201],
        "response": response.json()
        if response.status_code in [200, 201]
        else response.text,
        "payload": payload,
    }


def main():
    """Main function to read CSV and create datasets."""
    print("=" * 80)
    print("Adding Audio Classification Datasets via API")
    print("=" * 80)
    print(f"CSV File: {CSV_FILE}")
    print(f"API Endpoint: {API_BASE_URL}/datasets/")
    print(f"Task ID: {TASK_ID} (Audio Classification)")
    print("=" * 80)
    print()

    # Statistics
    total_datasets = 0
    successful_datasets = 0
    failed_datasets = 0
    duplicate_datasets = 0

    # Read CSV and process each dataset
    try:
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                total_datasets += 1
                dataset_name = row.get("Dataset", "Unknown")

                print(f"[{total_datasets}] Processing: {dataset_name}")

                # Create dataset via API
                result = create_dataset(row)

                if result["success"]:
                    successful_datasets += 1
                    response_data = result["response"]
                    dataset_id = response_data.get("id", "N/A")
                    dataset_slug = response_data.get("slug", "N/A")
                    print(
                        f"    ✓ Created successfully (ID: {dataset_id}, Slug: {dataset_slug})"
                    )
                else:
                    # Check if it's a duplicate
                    if (
                        result["status_code"] == 400
                        and "already exists" in str(result["response"]).lower()
                    ):
                        duplicate_datasets += 1
                        print("    ⚠ Already exists (duplicate)")
                    else:
                        failed_datasets += 1
                        print(f"    ✗ Failed (Status: {result['status_code']})")
                        print(f"    Error: {result['response']}")

                print()

    except FileNotFoundError:
        print(f"✗ Error: CSV file not found at {CSV_FILE}")
        return 1
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return 1

    # Print summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total datasets processed:  {total_datasets}")
    print(f"Successfully created:      {successful_datasets}")
    print(f"Duplicates (skipped):      {duplicate_datasets}")
    print(f"Failed:                    {failed_datasets}")
    print("=" * 80)

    if failed_datasets > 0:
        print("\n⚠ Some datasets failed to be created. Please review the errors above.")
        return 1
    else:
        print("\n✓ All datasets processed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
