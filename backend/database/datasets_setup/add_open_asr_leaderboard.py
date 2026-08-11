"""
Add Open ASR Leaderboard dataset using the API.

This script:
1. Creates the Open ASR Leaderboard as a parent dataset via the API
2. Links it to the Automatic Speech Recognition task
3. Updates existing ASR benchmark datasets to set their parent_dataset_id

Based on: https://arxiv.org/abs/2510.06961
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import requests
from backend.database.connection import DatabaseManager
from backend.models.database import Task as DBTask, Dataset as DBDataset

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# API configuration
API_BASE_URL = "http://localhost:8000/api/v1"

db_manager = DatabaseManager()


def create_parent_dataset_via_api():
    """Create the Open ASR Leaderboard parent dataset using the API."""

    logger.info("=" * 80)
    logger.info("CREATING OPEN ASR LEADERBOARD PARENT DATASET VIA API")
    logger.info("=" * 80)

    # First, get the ASR task ID
    session = db_manager.session_local()
    try:
        asr_task = (
            session.query(DBTask)
            .filter(DBTask.name == "Automatic Speech Recognition")
            .first()
        )

        if not asr_task:
            logger.error("✗ Automatic Speech Recognition task not found!")
            return None

        logger.info(f"✓ Found ASR task (ID: {asr_task.id})")
        task_id = asr_task.id
    finally:
        session.close()

    # Prepare the API request payload
    payload = {
        "name": "Open ASR Leaderboard",
        "full_name": "Open Automatic Speech Recognition Leaderboard",
        "description": (
            "The Open ASR Leaderboard is a comprehensive benchmark for evaluating "
            "Automatic Speech Recognition (ASR) models across 11 diverse datasets including "
            "LibriSpeech, Common Voice, FLEURS, TEDLIUM, AMI, Earnings-22, Gigaspeech, "
            "SPGISpeech, Voxpopuli, and Multilingual LibriSpeech. It measures both accuracy "
            "(Word Error Rate) and efficiency (Real-Time Factor)."
        ),
        "short_description": (
            "Comprehensive ASR benchmark across 11 diverse datasets measuring accuracy "
            "and efficiency of speech recognition models."
        ),
        "url": "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard",
        "hf_url": "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard",
        "homepage": "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard",
        "paper_url": "https://arxiv.org/abs/2510.06961",
        "task_ids": [task_id],
        "modalities": ["Audio", "Text"],
        "languages": ["English", "Multilingual"],
        "introduced_date": "2024-10-10",
    }

    # Make the API request
    logger.info(f"\nSending POST request to {API_BASE_URL}/datasets/")
    logger.info(f"Payload: {payload['name']}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/datasets/",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 201:
            dataset = response.json()
            logger.info("✓ Successfully created dataset!")
            logger.info(f"  ID: {dataset['id']}")
            logger.info(f"  Name: {dataset['name']}")
            logger.info(f"  Slug: {dataset['slug']}")
            return dataset
        elif response.status_code == 409:
            logger.warning("⚠ Dataset already exists (409 Conflict)")
            # Try to find it in the database
            session = db_manager.session_local()
            try:
                existing = (
                    session.query(DBDataset)
                    .filter(DBDataset.slug == "open-asr-leaderboard")
                    .first()
                )
                if existing:
                    logger.info(f"✓ Found existing dataset (ID: {existing.id})")
                    return {
                        "id": existing.id,
                        "name": existing.name,
                        "slug": existing.slug,
                    }
                else:
                    logger.error("✗ Dataset exists but could not be found in database")
                    return None
            finally:
                session.close()
        else:
            logger.error(f"✗ API request failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None

    except requests.exceptions.ConnectionError:
        logger.error("✗ Could not connect to API. Is the backend server running?")
        logger.error("  For local development, start the backend on a free port.")
        return None
    except Exception as e:
        logger.error(f"✗ Error creating dataset via API: {e}")
        return None


def link_child_datasets(parent_dataset_id: int):
    """Update child datasets to set their parent_dataset_id."""

    logger.info("\n" + "=" * 80)
    logger.info("LINKING CHILD DATASETS TO OPEN ASR LEADERBOARD")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Dataset name patterns to search for
        dataset_patterns = [
            "fleurs",
            "librispeech",
            "tedlium",
            "common voice",
            "ami",
            "earnings",
            "gigaspeech",
            "spgispeech",
            "voxpopuli",
        ]

        child_datasets = []
        for pattern in dataset_patterns:
            datasets = (
                session.query(DBDataset)
                .filter(DBDataset.name.ilike(f"%{pattern}%"))
                .all()
            )
            child_datasets.extend(datasets)

        logger.info(f"Found {len(child_datasets)} potential child datasets\n")

        updated_count = 0
        skipped_count = 0

        for dataset in child_datasets:
            if dataset.parent_dataset_id:
                logger.info(f"⊙ Skipping {dataset.name} (already has parent)")
                skipped_count += 1
                continue

            # Update the parent_dataset_id
            dataset.parent_dataset_id = parent_dataset_id
            dataset.variant_type = (
                "split"  # These are different evaluation splits/subsets
            )
            logger.info(f"✓ Linked {dataset.name} (ID: {dataset.id})")
            updated_count += 1

        # Commit the changes
        session.commit()

        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total datasets found: {len(child_datasets)}")
        logger.info(f"Datasets linked: {updated_count}")
        logger.info(f"Datasets skipped: {skipped_count}")

        return updated_count

    except Exception as e:
        logger.error(f"✗ Error linking child datasets: {e}")
        session.rollback()
        return 0
    finally:
        session.close()


def verify_results(parent_dataset_id: int):
    """Verify the dataset was created and linked correctly."""

    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION")
    logger.info("=" * 80)

    session = db_manager.session_local()

    try:
        # Get the parent dataset
        parent = (
            session.query(DBDataset).filter(DBDataset.id == parent_dataset_id).first()
        )

        if not parent:
            logger.error("✗ Parent dataset not found!")
            return False

        logger.info(f"✓ Parent dataset: {parent.name}")
        logger.info(f"  ID: {parent.id}")
        logger.info(f"  Slug: {parent.slug}")
        logger.info(f"  URL: {parent.url}")
        logger.info(f"  Paper URL: {parent.paper_url}")

        # Count child datasets
        children = (
            session.query(DBDataset)
            .filter(DBDataset.parent_dataset_id == parent_dataset_id)
            .all()
        )

        logger.info(f"\n✓ Child datasets: {len(children)}")
        for child in children:
            logger.info(
                f"  - {child.name} (ID: {child.id}, Type: {child.variant_type})"
            )

        # Check task linkage
        from backend.models.database import TaskDataset as DBTaskDataset

        task_links = (
            session.query(DBTaskDataset)
            .filter(DBTaskDataset.dataset_id == parent_dataset_id)
            .all()
        )

        logger.info(f"\n✓ Linked to {len(task_links)} task(s)")

        # Check via API
        logger.info(
            f"\n✓ API endpoint: http://localhost:8000/api/v1/datasets/{parent.slug}"
        )
        logger.info(
            f"✓ Frontend URL: http://167.235.148.241:8080/datasets/{parent.slug}"
        )

        return True

    except Exception as e:
        logger.error(f"✗ Error during verification: {e}")
        return False
    finally:
        session.close()


def main():
    """Main function to add Open ASR Leaderboard dataset."""

    logger.info("\n" + "=" * 80)
    logger.info("ADD OPEN ASR LEADERBOARD DATASET")
    logger.info("=" * 80)
    logger.info("Based on: https://arxiv.org/abs/2510.06961")
    logger.info("=" * 80 + "\n")

    # Step 1: Create parent dataset via API
    parent_dataset = create_parent_dataset_via_api()
    if not parent_dataset:
        logger.error("\n✗ Failed to create parent dataset. Exiting.")
        sys.exit(1)

    parent_id = parent_dataset["id"]

    # Step 2: Link child datasets
    linked_count = link_child_datasets(parent_id)
    if linked_count == 0:
        logger.warning("\n⚠ No child datasets were linked.")

    # Step 3: Verify results
    if verify_results(parent_id):
        logger.info("\n" + "=" * 80)
        logger.info("✅ SUCCESS!")
        logger.info("=" * 80)
        logger.info("The Open ASR Leaderboard has been added to the database.")
        logger.info(
            f"View it at: http://167.235.148.241:8080/datasets/{parent_dataset['slug']}"
        )
    else:
        logger.error("\n✗ Verification failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
