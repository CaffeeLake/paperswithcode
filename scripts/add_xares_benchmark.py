"""
Add X-ARES benchmark parent datasets and update child datasets to reference them.

X-ARES (eXtensive Audio Representation and Evaluation Suite) is an audio encoder
benchmark with two evaluation methods: kNN and MLP.
"""

import os
import requests
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# API configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TASK_ID = 259  # Audio Classification task ID

# Child dataset IDs (previously created audio classification datasets)
CHILD_DATASET_IDS = list(range(193, 214))  # IDs 193-213 (21 datasets)

# Database connection parameters
DB_CONFIG = {
    "host": os.getenv("PWC_DB_HOST"),
    "database": os.getenv("PWC_DB_NAME"),
    "user": os.getenv("PWC_DB_USER"),
    "password": os.getenv("PWC_DB_PASSWORD"),
}


def create_xares_parent_datasets():
    """
    Create X-ARES (kNN) and X-ARES (MLP) parent datasets via API.

    Returns:
        Tuple of (knn_dataset_id, mlp_dataset_id)
    """
    url = f"{API_BASE_URL}/datasets/"

    # X-ARES (kNN) dataset
    knn_payload = {
        "name": "X-ARES (kNN)",
        "description": "X-ARES (eXtensive Audio Representation and Evaluation Suite) is an audio encoder benchmark with kNN (K-nearest neighbor) evaluation method. This unparameterized evaluation uses pre-trained model embeddings directly for classification without training, testing the inherent quality of audio representations.",
        "url": "https://github.com/jimbozhang/xares",
        "paper_url": "https://arxiv.org/abs/2505.16369",
        "task_ids": [TASK_ID],
        "variant_type": "kNN",
    }

    # X-ARES (MLP) dataset
    mlp_payload = {
        "name": "X-ARES (MLP)",
        "description": "X-ARES (eXtensive Audio Representation and Evaluation Suite) is an audio encoder benchmark with MLP (Linear Fine-Tuning) evaluation method. This method trains a linear layer using provided embeddings with predefined hyperparameters, assessing how effectively fixed representations can be adapted to specific tasks.",
        "url": "https://github.com/jimbozhang/xares",
        "paper_url": "https://arxiv.org/abs/2505.16369",
        "task_ids": [TASK_ID],
        "variant_type": "MLP",
    }

    print("=" * 80)
    print("Creating X-ARES Parent Datasets")
    print("=" * 80)
    print()

    # Create kNN dataset
    print("[1/2] Creating X-ARES (kNN) dataset...")
    knn_response = requests.post(url, json=knn_payload)

    if knn_response.status_code in [200, 201]:
        knn_data = knn_response.json()
        knn_id = knn_data["id"]
        knn_slug = knn_data["slug"]
        print(f"      ✓ Created successfully (ID: {knn_id}, Slug: {knn_slug})")
    else:
        print(f"      ✗ Failed (Status: {knn_response.status_code})")
        print(f"      Error: {knn_response.text}")
        return None, None

    print()

    # Create MLP dataset
    print("[2/2] Creating X-ARES (MLP) dataset...")
    mlp_response = requests.post(url, json=mlp_payload)

    if mlp_response.status_code in [200, 201]:
        mlp_data = mlp_response.json()
        mlp_id = mlp_data["id"]
        mlp_slug = mlp_data["slug"]
        print(f"      ✓ Created successfully (ID: {mlp_id}, Slug: {mlp_slug})")
    else:
        print(f"      ✗ Failed (Status: {mlp_response.status_code})")
        print(f"      Error: {mlp_response.text}")
        return int(knn_id), None

    print()
    return int(knn_id), int(mlp_id)


def update_child_datasets_with_parents(knn_parent_id, mlp_parent_id):
    """
    Update child datasets to reference X-ARES parent datasets.

    Updates datasets with parent_dataset_id using SQL.

    Args:
        knn_parent_id: ID of X-ARES (kNN) parent dataset
        mlp_parent_id: ID of X-ARES (MLP) parent dataset

    Returns:
        Number of datasets successfully updated
    """
    print("=" * 80)
    print("Updating Child Datasets with Parent References")
    print("=" * 80)
    print()

    # For now, we'll link all child datasets to the kNN parent
    # In a real scenario, you might want to split them based on evaluation method
    parent_id = knn_parent_id

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get dataset names before update
        cursor.execute(
            """
            SELECT id, name, slug
            FROM datasets
            WHERE id = ANY(%s)
            ORDER BY id
            """,
            (CHILD_DATASET_IDS,),
        )
        datasets = cursor.fetchall()

        if len(datasets) != len(CHILD_DATASET_IDS):
            print(
                f"⚠ Warning: Expected {len(CHILD_DATASET_IDS)} datasets, found {len(datasets)}"
            )

        print(
            f"Updating {len(datasets)} datasets to reference parent dataset ID {parent_id}..."
        )
        print()

        # Update all child datasets to reference the parent
        cursor.execute(
            """
            UPDATE datasets
            SET parent_dataset_id = %s
            WHERE id = ANY(%s)
            """,
            (parent_id, CHILD_DATASET_IDS),
        )

        updated_count = cursor.rowcount
        conn.commit()

        # Show updated datasets
        for i, dataset in enumerate(datasets, 1):
            print(
                f"  [{i:2d}] {dataset['name']:35s} (ID: {dataset['id']}, Slug: {dataset['slug']})"
            )

        print()
        print(f"✓ Successfully updated {updated_count} datasets with parent reference")

        cursor.close()
        conn.close()

        return updated_count

    except Exception as e:
        print(f"✗ Error updating datasets: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        return 0


def verify_relationships(knn_parent_id, mlp_parent_id):
    """
    Verify that parent-child relationships are correctly established.

    Args:
        knn_parent_id: ID of X-ARES (kNN) parent dataset
        mlp_parent_id: ID of X-ARES (MLP) parent dataset
    """
    print()
    print("=" * 80)
    print("Verification")
    print("=" * 80)
    print()

    # Verify parent datasets
    print("[1/3] Verifying parent datasets...")

    knn_url = f"{API_BASE_URL}/datasets/{knn_parent_id}"
    knn_response = requests.get(knn_url)

    if knn_response.status_code == 200:
        knn_data = knn_response.json()
        print(f"      ✓ X-ARES (kNN) - ID: {knn_data['id']}, Slug: {knn_data['slug']}")
    else:
        print("      ✗ X-ARES (kNN) not found")

    mlp_url = f"{API_BASE_URL}/datasets/{mlp_parent_id}"
    mlp_response = requests.get(mlp_url)

    if mlp_response.status_code == 200:
        mlp_data = mlp_response.json()
        print(f"      ✓ X-ARES (MLP) - ID: {mlp_data['id']}, Slug: {mlp_data['slug']}")
    else:
        print("      ✗ X-ARES (MLP) not found")

    print()

    # Verify child datasets
    print("[2/3] Verifying child datasets reference parent...")

    sample_ids = [193, 200, 213]  # Sample a few datasets

    for dataset_id in sample_ids:
        url = f"{API_BASE_URL}/datasets/{dataset_id}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            parent_id = data.get("parent_dataset_id")

            if parent_id == str(knn_parent_id):
                print(
                    f"      ✓ Dataset {data['name']} (ID: {dataset_id}) → Parent: {parent_id}"
                )
            else:
                print(
                    f"      ✗ Dataset {data['name']} (ID: {dataset_id}) → Parent: {parent_id} (expected {knn_parent_id})"
                )
        else:
            print(f"      ✗ Dataset ID {dataset_id} not found")

    print()

    # Database verification
    print("[3/3] Database verification...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM datasets
            WHERE parent_dataset_id = %s
            """,
            (knn_parent_id,),
        )
        result = cursor.fetchone()
        child_count = result["count"]

        print(f"      ✓ {child_count} datasets linked to X-ARES (kNN) parent")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"      ✗ Database verification failed: {str(e)}")


def main():
    """Main function to create X-ARES benchmarks and update child datasets."""
    print("=" * 80)
    print("X-ARES Benchmark Setup")
    print("=" * 80)
    print("Creating parent datasets and updating child dataset references")
    print("=" * 80)
    print()

    # Step 1: Create parent datasets
    knn_parent_id, mlp_parent_id = create_xares_parent_datasets()

    if not knn_parent_id or not mlp_parent_id:
        print("✗ Failed to create parent datasets. Aborting.")
        return 1

    print()

    # Step 2: Update child datasets
    updated_count = update_child_datasets_with_parents(knn_parent_id, mlp_parent_id)

    if updated_count == 0:
        print("✗ Failed to update child datasets. Aborting.")
        return 1

    # Step 3: Verify relationships
    verify_relationships(knn_parent_id, mlp_parent_id)

    # Final summary
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print("✓ Created 2 parent datasets:")
    print(f"  - X-ARES (kNN) - ID: {knn_parent_id}")
    print(f"  - X-ARES (MLP) - ID: {mlp_parent_id}")
    print(f"✓ Updated {updated_count} child datasets with parent references")
    print("=" * 80)
    print()
    print("✓ X-ARES benchmark setup complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
