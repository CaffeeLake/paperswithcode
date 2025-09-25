#!/usr/bin/env python3
"""
Extract ArXiv IDs from paperswithcode_hf database and save to CSV file.
This script queries the database to get all unique ArXiv IDs for PDF downloading.
"""

import csv
import logging
import sys
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.append(str(Path(__file__).parent.parent))

from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_arxiv_ids_from_database(output_file: str = "arxiv_ids_for_download.csv"):
    """
    Extract all unique ArXiv IDs from the paperswithcode_hf database.

    Args:
        output_file: Path to output CSV file
    """
    try:
        # Get database session
        db_session_gen = get_database_session()
        db_session = next(db_session_gen)

        try:
            paper_service = PaperService(db_session)

            # Test connection and get stats
            stats = paper_service.get_paper_stats()
            logger.info("✅ Database connection successful!")
            logger.info(f"Total papers in database: {stats['total_papers']:,}")

            # Query for all unique ArXiv IDs
            from sqlalchemy import text

            query = """
            SELECT DISTINCT arxiv_id
            FROM papers
            WHERE arxiv_id IS NOT NULL
            AND arxiv_id != ''
            ORDER BY arxiv_id
            """

            result = db_session.execute(text(query))
            arxiv_ids = [row.arxiv_id for row in result.fetchall()]

            logger.info(f"Found {len(arxiv_ids)} unique ArXiv IDs")

            # Write to CSV file
            output_path = Path(output_file)
            with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["arxiv_id"])  # Header

                for arxiv_id in arxiv_ids:
                    writer.writerow([arxiv_id])

            logger.info(
                f"✅ Successfully wrote {len(arxiv_ids)} ArXiv IDs to {output_path.absolute()}"
            )

            # Show some sample IDs
            if arxiv_ids:
                logger.info("Sample ArXiv IDs:")
                for i, arxiv_id in enumerate(arxiv_ids[:10]):
                    logger.info(f"  {i + 1}. {arxiv_id}")
                if len(arxiv_ids) > 10:
                    logger.info(f"  ... and {len(arxiv_ids) - 10} more")

            return len(arxiv_ids)

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error extracting ArXiv IDs: {e}")
        return 0


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract ArXiv IDs from database")
    parser.add_argument(
        "--output", default="arxiv_ids_for_download.csv", help="Output CSV file path"
    )

    args = parser.parse_args()

    count = extract_arxiv_ids_from_database(args.output)

    if count > 0:
        logger.info(
            f"✅ Extraction complete! {count} ArXiv IDs ready for PDF download."
        )
    else:
        logger.error("❌ Extraction failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
