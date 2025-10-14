#!/usr/bin/env python3
"""
Update proceedings column for ICCV 2025 accepted papers.

This script:
1. Loads the ICCV 2025 dataset from Hugging Face
2. Matches papers with the database based on arxiv_id
3. Updates the proceedings column to include "ICCV 2025"
"""

import psycopg2
from datasets import load_dataset
import logging
from typing import Set

from backend.config import get_settings

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_iccv2025_arxiv_ids() -> Set[str]:
    """
    Load ICCV 2025 dataset and extract all arxiv_ids.

    Returns:
        Set of arxiv_ids from ICCV 2025 accepted papers
    """
    logger.info("Loading ICCV 2025 dataset from Hugging Face...")

    try:
        dataset = load_dataset("ai-conferences/ICCV2025", split="train")
        logger.info(f"Loaded {len(dataset)} papers from ICCV 2025 dataset")

        # Extract arxiv_ids (filter out None values)
        arxiv_ids = set()
        for paper in dataset:
            arxiv_id = paper.get("arxiv_id")
            if arxiv_id:
                arxiv_ids.add(arxiv_id)

        logger.info(f"Found {len(arxiv_ids)} papers with arxiv_ids")
        return arxiv_ids

    except Exception as e:
        logger.error(f"Error loading dataset: {e}")
        raise


def get_db_connection():
    """Get database connection."""
    settings = get_settings()
    return psycopg2.connect(
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password if settings.db_password else None,
        host=settings.db_host,
        port=settings.db_port,
    )


def update_proceedings_for_paper(
    cursor, arxiv_id: str, proceeding_text: str = "ICCV 2025"
) -> bool:
    """
    Update the proceeding column for a paper with the given arxiv_id.

    Args:
        cursor: Database cursor
        arxiv_id: ArXiv ID of the paper
        proceeding_text: Proceeding text to add

    Returns:
        True if paper was updated, False if not found
    """
    # First, check if the paper exists and get its current proceeding
    cursor.execute("SELECT id, proceeding FROM papers WHERE arxiv_id = %s", (arxiv_id,))

    result = cursor.fetchone()
    if not result:
        return False

    paper_id, current_proceeding = result

    # Check if ICCV 2025 is already in proceeding
    if current_proceeding and "ICCV 2025" in current_proceeding:
        logger.debug(f"Paper {arxiv_id} already has ICCV 2025 in proceeding")
        return False

    # Add ICCV 2025 to proceeding
    if current_proceeding:
        new_proceeding = f"{current_proceeding}, {proceeding_text}"
    else:
        new_proceeding = proceeding_text

    # Update the paper
    cursor.execute(
        "UPDATE papers SET proceeding = %s WHERE id = %s", (new_proceeding, paper_id)
    )

    return True


def main():
    """Main function to update ICCV 2025 proceedings."""
    logger.info("Starting ICCV 2025 proceedings update...")

    # Load ICCV 2025 arxiv_ids
    iccv_arxiv_ids = load_iccv2025_arxiv_ids()

    if not iccv_arxiv_ids:
        logger.warning("No arxiv_ids found in ICCV 2025 dataset")
        return

    # Connect to database and update papers
    logger.info("Connecting to database...")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                updated_count = 0
                not_found_count = 0

                logger.info(f"Processing {len(iccv_arxiv_ids)} ICCV 2025 papers...")

                for i, arxiv_id in enumerate(iccv_arxiv_ids, 1):
                    if i % 100 == 0:
                        logger.info(f"Processed {i}/{len(iccv_arxiv_ids)} papers...")

                    was_updated = update_proceedings_for_paper(cursor, arxiv_id)

                    if was_updated:
                        updated_count += 1
                    else:
                        not_found_count += 1

                # Commit all changes
                conn.commit()

                logger.info("=" * 60)
                logger.info("Update complete!")
                logger.info(f"Papers updated: {updated_count}")
                logger.info(f"Papers not found in database: {not_found_count}")
                logger.info(f"Total ICCV 2025 papers: {len(iccv_arxiv_ids)}")
                logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error updating proceedings: {e}")
        raise


if __name__ == "__main__":
    main()
