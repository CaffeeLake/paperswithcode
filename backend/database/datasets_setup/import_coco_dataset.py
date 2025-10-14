"""
Import COCO dataset from legacy PapersWithCode datasets.json file.

This script demonstrates importing a single high-quality dataset (COCO test-dev)
from the legacy PWC data dump. This can be extended to import more datasets later.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Parse a date string to a date object."""
    if not date_str:
        return None

    try:
        # Try parsing as YYYY-MM-DD
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            # Try parsing as YYYY-MM
            return datetime.strptime(f"{date_str}-01", "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")
            return None


def find_coco_dataset(datasets_file: Path) -> Optional[dict]:
    """Find the main COCO dataset entry from the datasets file."""
    logger.info(f"Loading datasets from {datasets_file}")

    with open(datasets_file, "r", encoding="utf-8") as f:
        datasets = json.load(f)

    # Find the main COCO dataset (not variants like COCO-Stuff, COCO-Text, etc.)
    for dataset in datasets:
        # Look for the main COCO dataset
        if dataset.get("name") == "COCO (Common Objects in Context)":
            logger.info(f"Found COCO dataset: {dataset['name']}")
            return dataset

    logger.error("COCO dataset not found in datasets file")
    return None


def import_dataset(db: Session, dataset_data: dict) -> Optional[DBDataset]:
    """Import a dataset into the database."""

    # Check if dataset already exists
    existing = (
        db.query(DBDataset).filter(DBDataset.name == dataset_data["name"]).first()
    )
    if existing:
        logger.info(
            f"Dataset already exists: {dataset_data['name']} (ID: {existing.id})"
        )
        return existing

    # Parse the introducing paper
    introducing_paper_title = None
    if dataset_data.get("verified_paper"):
        introducing_paper_title = dataset_data["verified_paper"].get("title")
    elif dataset_data.get("paper"):
        introducing_paper_title = dataset_data["paper"].get("title")

    # Create the dataset
    dataset = DBDataset(
        name=dataset_data.get("name"),
        full_name=dataset_data.get("full_name") or dataset_data.get("verified_name"),
        description=dataset_data.get("description"),
        short_description=dataset_data.get("short_description"),
        url=dataset_data.get("url"),  # This is the PWC page URL
        pwc_url=dataset_data.get("url"),
        homepage=dataset_data.get("homepage"),
        # Images
        image_url=dataset_data.get("image"),
        thumbnail_url=dataset_data.get("thumbnail"),
        verified_image_url=dataset_data.get("verified_image"),
        # Paper reference
        introducing_paper_title=introducing_paper_title,
        # License
        license_name=dataset_data.get("license_name"),
        license_url=dataset_data.get("license_url"),
        # Date
        introduced_date=parse_date(dataset_data.get("introduced_date")),
        # Arrays (stored as JSONB)
        modalities=dataset_data.get("modalities"),
        languages=dataset_data.get("languages"),
        variants=dataset_data.get("variants"),
        # Counts
        num_papers=dataset_data.get("num_papers", 0),
        # Warning
        warning=dataset_data.get("warning"),
    )

    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    logger.info(f"Successfully imported dataset: {dataset.name} (ID: {dataset.id})")
    logger.info(f"  - Full name: {dataset.full_name}")
    logger.info(f"  - Introduced: {dataset.introduced_date}")
    logger.info(f"  - Modalities: {dataset.modalities}")
    logger.info(
        f"  - Variants: {len(dataset.variants) if dataset.variants else 0} variants"
    )
    logger.info(f"  - Papers using it: {dataset.num_papers}")

    return dataset


def main():
    """Main function to import COCO dataset."""
    # Path to the legacy PWC datasets file
    datasets_file = (
        Path(__file__).parent.parent.parent.parent
        / "data"
        / "legacy_pwc_data"
        / "jul-28-datasets.json"
    )

    if not datasets_file.exists():
        logger.error(f"Datasets file not found: {datasets_file}")
        return

    # Find COCO dataset
    coco_data = find_coco_dataset(datasets_file)
    if not coco_data:
        logger.error("Could not find COCO dataset in the file")
        return

    # Import to database
    session = db_manager.session_local()
    try:
        dataset = import_dataset(session, coco_data)

        if dataset:
            logger.info("\n" + "=" * 60)
            logger.info("COCO Dataset Import Summary")
            logger.info("=" * 60)
            logger.info(f"Database ID: {dataset.id}")
            logger.info(f"Name: {dataset.name}")
            logger.info(f"Full Name: {dataset.full_name}")
            logger.info(f"Homepage: {dataset.homepage}")
            logger.info(f"PWC URL: {dataset.pwc_url}")
            logger.info(f"Introduced: {dataset.introduced_date}")
            logger.info(f"License: {dataset.license_name}")
            logger.info(
                f"Modalities: {', '.join(dataset.modalities) if dataset.modalities else 'None'}"
            )
            logger.info(
                f"Languages: {', '.join(dataset.languages) if dataset.languages else 'None'}"
            )
            logger.info(
                f"Number of variants: {len(dataset.variants) if dataset.variants else 0}"
            )

            if dataset.variants:
                logger.info("\nVariants (first 10):")
                for variant in (dataset.variants or [])[:10]:
                    logger.info(f"  - {variant}")

            logger.info(f"\nPapers using this dataset: {dataset.num_papers}")
            logger.info("=" * 60)

            # Check if COCO test-dev is in variants
            if dataset.variants and "COCO test-dev" in dataset.variants:
                logger.info("\n✓ SUCCESS: 'COCO test-dev' variant is included!")
            else:
                logger.warning(
                    "\n⚠ WARNING: 'COCO test-dev' variant not found in the dataset"
                )
    finally:
        session.close()


if __name__ == "__main__":
    main()
