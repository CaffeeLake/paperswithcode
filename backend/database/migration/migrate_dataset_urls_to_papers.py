"""Migrate dataset URLs to paper-level repositories and project pages.

This migration moves URLs stored on datasets to the corresponding papers by
creating `paper_repositories` or `paper_project_pages` links. After the
migration, dataset URLs are cleared so the canonical links live on the paper.

Usage:
    uv run --env-file backend/keys.env \
        python backend/database/migration/migrate_dataset_urls_to_papers.py

Add `--dry-run` to preview changes without committing them.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Dataset,
    Paper,
    PaperProjectPage,
    PaperRepository,
    ProjectPage,
    Repository,
)
from backend.utils.github_utils import normalize_github_url, parse_github_url


logger = logging.getLogger(__name__)


ARXIV_PATTERNS = (
    re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)(?:v\d+)?", re.IGNORECASE),
    re.compile(r"huggingface\.co/papers/([0-9.]+)(?:v\d+)?", re.IGNORECASE),
)


@dataclass
class MigrationStats:
    """Simple container for migration metrics."""

    datasets_processed: int = 0
    datasets_migrated: int = 0
    datasets_cleared: int = 0
    datasets_missing_paper: int = 0
    datasets_invalid_url: int = 0
    repositories_created: int = 0
    repositories_linked: int = 0
    repositories_existing_link: int = 0
    project_pages_created: int = 0
    project_pages_linked: int = 0
    project_pages_existing_link: int = 0
    datasets_linked_via_arxiv: int = 0


def extract_arxiv_id(paper_url: Optional[str]) -> Optional[str]:
    """Return the base arXiv identifier from a paper URL if possible."""

    if not paper_url:
        return None

    for pattern in ARXIV_PATTERNS:
        match = pattern.search(paper_url)
        if match:
            return match.group(1)

    return None


def normalize_project_page_url(url: str) -> Optional[str]:
    """Normalize project page URL by standardising scheme, host and path."""

    if not url:
        return None

    cleaned = url.strip()
    if not cleaned:
        return None

    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return None

    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    normalized = urlunparse((scheme, netloc, path, "", "", ""))

    return normalized


def get_paper_for_dataset(
    session: Session, dataset: Dataset
) -> Tuple[Optional[Paper], bool]:
    """Resolve the paper associated with the dataset, if any."""

    if dataset.introducing_paper_id:
        paper = session.get(Paper, dataset.introducing_paper_id)
        if paper:
            return paper, False

    arxiv_id = extract_arxiv_id(dataset.paper_url)
    if not arxiv_id:
        return None, False

    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if not paper:
        paper = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id)
            .order_by(Paper.updated_at.desc())
            .first()
        )

    inferred = False
    if paper and dataset.introducing_paper_id is None:
        dataset.introducing_paper_id = paper.id
        inferred = True

    return paper, inferred


def get_or_create_repository(
    session: Session, url: str, stats: MigrationStats
) -> Optional[Repository]:
    """Return a repository row for the GitHub URL, creating if needed."""

    normalized_url = normalize_github_url(url)
    if not normalized_url:
        return None

    repository = (
        session.query(Repository).filter(Repository.url == normalized_url).first()
    )
    if repository:
        return repository

    owner, name = parse_github_url(normalized_url)
    if not owner or not name:
        return None

    repository = Repository(
        url=normalized_url,
        owner=owner,
        name=name,
        source="dataset_url_migration",
    )
    session.add(repository)
    session.flush()
    stats.repositories_created += 1
    logger.info("Created repository %s", normalized_url)
    return repository


def link_repository_to_paper(
    session: Session, paper: Paper, repository: Repository, stats: MigrationStats
) -> None:
    """Ensure the paper is linked to the repository."""

    exists = (
        session.query(PaperRepository)
        .filter(
            PaperRepository.paper_id == paper.id,
            PaperRepository.repository_id == repository.id,
        )
        .first()
    )

    if exists:
        stats.repositories_existing_link += 1
        return

    session.add(
        PaperRepository(
            paper_id=paper.id,
            repository_id=repository.id,
            is_official=True,
        )
    )
    session.flush()
    stats.repositories_linked += 1
    logger.info("Linked paper %s to repository %s", paper.id, repository.url)


def get_or_create_project_page(
    session: Session, url: str, stats: MigrationStats
) -> Optional[ProjectPage]:
    """Return a project page row for the URL, creating if necessary."""

    normalized_url = normalize_project_page_url(url)
    if not normalized_url:
        return None

    project_page = (
        session.query(ProjectPage).filter(ProjectPage.url == normalized_url).first()
    )
    if project_page:
        return project_page

    project_page = ProjectPage(
        url=normalized_url,
        is_official=True,
        source="dataset_url_migration",
    )
    session.add(project_page)
    session.flush()
    stats.project_pages_created += 1
    logger.info("Created project page %s", normalized_url)
    return project_page


def link_project_page_to_paper(
    session: Session, paper: Paper, project_page: ProjectPage, stats: MigrationStats
) -> None:
    """Ensure the paper is linked to the project page."""

    exists = (
        session.query(PaperProjectPage)
        .filter(
            PaperProjectPage.paper_id == paper.id,
            PaperProjectPage.project_page_id == project_page.id,
        )
        .first()
    )

    if exists:
        stats.project_pages_existing_link += 1
        return

    session.add(PaperProjectPage(paper_id=paper.id, project_page_id=project_page.id))
    session.flush()
    stats.project_pages_linked += 1
    logger.info("Linked paper %s to project page %s", paper.id, project_page.url)


def migrate_dataset(session: Session, dataset: Dataset, stats: MigrationStats) -> None:
    """Migrate a single dataset URL to paper-level storage."""

    stats.datasets_processed += 1

    paper, inferred = get_paper_for_dataset(session, dataset)
    if not paper:
        stats.datasets_missing_paper += 1
        logger.info(
            "Skipping dataset %s (%s): no linked paper found",
            dataset.id,
            dataset.name,
        )
        return

    if inferred:
        stats.datasets_linked_via_arxiv += 1

    if not dataset.url:
        stats.datasets_invalid_url += 1
        return

    raw_url = dataset.url.strip()
    if not raw_url:
        stats.datasets_invalid_url += 1
        return

    migrated = False

    if "github.com" in raw_url.lower():
        repository = get_or_create_repository(session, raw_url, stats)
        if not repository:
            stats.datasets_invalid_url += 1
            logger.warning(
                "Dataset %s (%s) has invalid GitHub URL: %s",
                dataset.id,
                dataset.name,
                raw_url,
            )
            return

        link_repository_to_paper(session, paper, repository, stats)
        migrated = True

    else:
        project_page = get_or_create_project_page(session, raw_url, stats)
        if not project_page:
            stats.datasets_invalid_url += 1
            logger.warning(
                "Dataset %s (%s) has invalid project page URL: %s",
                dataset.id,
                dataset.name,
                raw_url,
            )
            return

        link_project_page_to_paper(session, paper, project_page, stats)
        migrated = True

    if migrated:
        stats.datasets_migrated += 1
        dataset.url = None
        stats.datasets_cleared += 1
        logger.info(
            "Cleared dataset URL after migration for dataset %s (%s)",
            dataset.id,
            dataset.name,
        )


def migrate(session: Session) -> MigrationStats:
    """Run the migration for all datasets with URLs."""

    stats = MigrationStats()

    datasets = (
        session.query(Dataset)
        .filter(Dataset.url.isnot(None))
        .order_by(Dataset.id)
        .all()
    )

    logger.info("Found %s datasets with URLs to migrate", len(datasets))

    for dataset in datasets:
        migrate_dataset(session, dataset, stats)

    return stats


def print_summary(stats: MigrationStats) -> None:
    """Log migration summary stats."""

    logger.info("\n%s", "=" * 80)
    logger.info("DATASET URL MIGRATION SUMMARY")
    logger.info("%s", "=" * 80)
    logger.info("Datasets processed: %s", stats.datasets_processed)
    logger.info("Datasets migrated: %s", stats.datasets_migrated)
    logger.info("Datasets cleared: %s", stats.datasets_cleared)
    logger.info("Datasets skipped (missing paper): %s", stats.datasets_missing_paper)
    logger.info("Datasets skipped (invalid URL): %s", stats.datasets_invalid_url)
    logger.info("Repositories created: %s", stats.repositories_created)
    logger.info("Repositories linked: %s", stats.repositories_linked)
    logger.info("Repositories already linked: %s", stats.repositories_existing_link)
    logger.info("Project pages created: %s", stats.project_pages_created)
    logger.info("Project pages linked: %s", stats.project_pages_linked)
    logger.info("Project pages already linked: %s", stats.project_pages_existing_link)
    logger.info(
        "Datasets linked via inferred introducing_paper_id: %s",
        stats.datasets_linked_via_arxiv,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate dataset URLs to paper repositories/project pages"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run migration without committing changes",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    session = db_manager.session_local()

    try:
        stats = migrate(session)
        print_summary(stats)

        if args.dry_run:
            session.rollback()
            logger.info("Dry run complete — no changes committed")
        else:
            session.commit()
            logger.info("Migration committed successfully")

    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        logger.exception("Migration failed: %s", exc)
        raise
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    main()
