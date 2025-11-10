"""
Add missing papers for datasets that have paper URLs but no linked papers.

This script:
1. Finds all datasets with paper_url but missing introducing_paper_id
2. Extracts ArXiv IDs from paper URLs
3. Checks if papers exist in the database
4. Fetches missing papers from ArXiv API
5. Adds them to the database
6. Links them to the datasets

Usage:
    uv run --env-file backend/keys.env python backend/database/papers_setup/add_missing_dataset_papers.py
"""

import asyncio
import logging
import re
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Paper, Author, PaperAuthor
from backend.services.paper_service import PaperService
from backend.services.arxiv_service import ArxivService
from backend.utils.urls import extract_arxiv_id_from_text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ArXiv URL patterns
ARXIV_PATTERNS = (
    re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)(?:v\d+)?", re.IGNORECASE),
    re.compile(r"huggingface\.co/papers/([0-9.]+)(?:v\d+)?", re.IGNORECASE),
)


def extract_arxiv_id_from_url(paper_url: Optional[str]) -> Optional[str]:
    """Extract ArXiv ID from a paper URL."""
    if not paper_url:
        return None

    # Try URL patterns first
    for pattern in ARXIV_PATTERNS:
        match = pattern.search(paper_url)
        if match:
            arxiv_id = match.group(1)
            # Remove trailing periods and clean up
            arxiv_id = arxiv_id.rstrip(".")
            return arxiv_id

    # Fall back to text extraction
    arxiv_id = extract_arxiv_id_from_text(paper_url)
    if arxiv_id:
        # Remove trailing periods
        arxiv_id = arxiv_id.rstrip(".")
    return arxiv_id


def get_datasets_with_missing_papers(
    session: Session,
) -> List[Tuple[Dataset, str, Optional[Paper]]]:
    """
    Find all datasets that have paper_url but no valid introducing_paper_id.

    Returns:
        List of tuples: (dataset, arxiv_id, existing_paper_or_none)
    """
    datasets = (
        session.query(Dataset)
        .filter(
            Dataset.paper_url.isnot(None),
            Dataset.paper_url != "",
        )
        .all()
    )

    # Filter to only those where the paper doesn't exist
    result = []
    for dataset in datasets:
        # If introducing_paper_id exists, check if paper still exists
        if dataset.introducing_paper_id:
            paper = session.get(Paper, dataset.introducing_paper_id)
            if paper:
                continue  # Paper exists, skip

        # Extract ArXiv ID from URL
        arxiv_id = extract_arxiv_id_from_url(dataset.paper_url)
        if not arxiv_id:
            logger.warning(
                f"Dataset '{dataset.name}' (ID: {dataset.id}) has paper_url but "
                f"could not extract ArXiv ID: {dataset.paper_url}"
            )
            continue

        # Check if paper already exists in database
        existing_paper = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )

        if existing_paper:
            # Paper exists but not linked - we'll link it
            logger.info(
                f"Dataset '{dataset.name}' has paper_url but paper already exists "
                f"(ID: {existing_paper.id}). Will link them."
            )
            result.append((dataset, arxiv_id, existing_paper))
        else:
            # Paper doesn't exist - need to fetch from ArXiv
            result.append((dataset, arxiv_id, None))

    return result


async def fetch_and_add_paper(
    arxiv_service: ArxivService,
    paper_service: PaperService,
    arxiv_id: str,
) -> Optional[Paper]:
    """
    Fetch paper from ArXiv API and add to database.

    Returns:
        Paper object if successful, None otherwise
    """
    logger.info(f"Fetching paper from ArXiv: {arxiv_id}")

    # Fetch metadata from ArXiv
    metadata = await arxiv_service.get_paper_metadata(arxiv_id)

    if not metadata.success:
        logger.error(
            f"Failed to fetch paper {arxiv_id} from ArXiv: {metadata.error_message}"
        )
        return None

    # Check if paper already exists (race condition check)
    existing = (
        paper_service.db.query(Paper)
        .filter(Paper.arxiv_id == metadata.arxiv_id, Paper.version == metadata.version)
        .first()
    )

    if existing:
        logger.info(f"Paper {arxiv_id} already exists in database (ID: {existing.id})")
        return existing

    # Prepare paper data
    paper_data = {
        "arxiv_id": metadata.arxiv_id,
        "title": metadata.title,
        "abstract": metadata.abstract,
        "version": metadata.version,
        "date_published": metadata.published.date() if metadata.published else None,
        "primary_category": metadata.primary_category,
        "all_categories": metadata.categories,
        "is_latest_version": True,  # We'll update this if needed
    }

    # Add paper to database
    paper_id = paper_service.add_paper(paper_data)

    if not paper_id:
        logger.error(f"Failed to add paper {arxiv_id} to database")
        return None

    logger.info(f"Successfully added paper {arxiv_id} (ID: {paper_id})")

    # Get the paper object
    paper = paper_service.db.get(Paper, paper_id)

    # Add authors if available
    if metadata.authors:
        await add_authors_to_paper(paper_service.db, paper, metadata.authors)

    return paper


async def add_authors_to_paper(session: Session, paper: Paper, author_names: List[str]):
    """Add authors to a paper."""
    from backend.database.authors_setup.populate_missing_authors_from_arxiv import (
        ArxivAuthorNameParser,
    )

    parser = ArxivAuthorNameParser()

    for order, full_name in enumerate(author_names, start=1):
        # Parse author name
        name = parser.parse_name(full_name)

        # Find or create author
        author = session.query(Author).filter(Author.name == name).first()

        if not author:
            author = Author(name=name)
            session.add(author)
            session.flush()  # Get the ID

        # Check if link already exists
        existing_link = (
            session.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id, PaperAuthor.author_id == author.id
            )
            .first()
        )

        if not existing_link:
            paper_author = PaperAuthor(
                paper_id=paper.id, author_id=author.id, author_order=order
            )
            session.add(paper_author)

    try:
        session.commit()
        logger.debug(f"Added {len(author_names)} authors to paper {paper.arxiv_id}")
    except Exception as e:
        session.rollback()
        logger.warning(f"Failed to add authors to paper {paper.arxiv_id}: {e}")


async def link_paper_to_dataset(
    session: Session, dataset: Dataset, paper: Paper
) -> bool:
    """Link a paper to a dataset by setting introducing_paper_id."""
    try:
        dataset.introducing_paper_id = paper.id
        if not dataset.introducing_paper_title:
            dataset.introducing_paper_title = paper.title
        session.commit()
        logger.info(
            f"Linked paper {paper.arxiv_id} (ID: {paper.id}) to dataset "
            f"'{dataset.name}' (ID: {dataset.id})"
        )
        return True
    except Exception as e:
        session.rollback()
        logger.error(
            f"Failed to link paper {paper.arxiv_id} to dataset '{dataset.name}': {e}"
        )
        return False


async def main():
    """Main function to find and add missing papers."""
    arxiv_service = ArxivService()

    with db_manager.session_local() as session:
        paper_service = PaperService(session)

        # Find datasets with missing papers
        logger.info("Finding datasets with missing papers...")
        datasets_info = get_datasets_with_missing_papers(session)

        if not datasets_info:
            logger.info("No datasets with missing papers found.")
            return

        logger.info(f"Found {len(datasets_info)} datasets with missing papers")

        # Process each dataset
        added_count = 0
        linked_count = 0
        error_count = 0

        for dataset, arxiv_id, existing_paper in datasets_info:
            try:
                if existing_paper:
                    # Paper exists, just link it
                    success = await link_paper_to_dataset(
                        session, dataset, existing_paper
                    )
                    if success:
                        linked_count += 1
                else:
                    # Paper doesn't exist, fetch and add it
                    paper = await fetch_and_add_paper(
                        arxiv_service, paper_service, arxiv_id
                    )

                    if paper:
                        # Link paper to dataset
                        success = await link_paper_to_dataset(session, dataset, paper)
                        if success:
                            added_count += 1
                    else:
                        error_count += 1
                        logger.warning(
                            f"Could not add paper for dataset '{dataset.name}' "
                            f"(ArXiv ID: {arxiv_id})"
                        )

            except Exception as e:
                error_count += 1
                logger.error(
                    f"Error processing dataset '{dataset.name}' (ArXiv ID: {arxiv_id}): {e}",
                    exc_info=True,
                )

        # Summary
        logger.info("=" * 60)
        logger.info("Summary:")
        logger.info(f"  Datasets processed: {len(datasets_info)}")
        logger.info(f"  Papers added: {added_count}")
        logger.info(f"  Papers linked: {linked_count}")
        logger.info(f"  Errors: {error_count}")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
