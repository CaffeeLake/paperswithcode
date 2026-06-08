"""
Backfill missing datasets.hf_url from Hugging Face datasets linked to source papers.

For benchmarks with introducing_paper_id pointing at an arXiv paper, this script
queries https://huggingface.co/api/arxiv/{arxiv_id}/repos and fills hf_url when
there is a single linked dataset or an unambiguous name/slug match.

Usage:
    uv run --env-file backend/keys.env python \\
        backend/database/datasets_setup/backfill_hf_urls_from_source_papers.py

    uv run --env-file backend/keys.env python \\
        backend/database/datasets_setup/backfill_hf_urls_from_source_papers.py --apply
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Paper
from backend.utils.benchmark_hf_url import pick_hf_dataset_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HF_ARXIV_REPOS_URL = "https://huggingface.co/api/arxiv/{arxiv_id}/repos"


@dataclass
class BackfillStats:
    scanned: int = 0
    updated: int = 0
    skipped_no_paper: int = 0
    skipped_no_arxiv: int = 0
    skipped_no_hf_datasets: int = 0
    skipped_ambiguous: int = 0
    skipped_api_error: int = 0
    skipped_already_set: int = 0


def fetch_hf_dataset_repo_ids(
    arxiv_id: str, session: requests.Session
) -> Optional[list[str]]:
    """Return HF dataset repo ids linked to an arXiv paper, or None on API failure."""
    url = HF_ARXIV_REPOS_URL.format(arxiv_id=arxiv_id)
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("HF API error for arXiv %s: %s", arxiv_id, exc)
        return None

    payload = response.json()
    datasets = payload.get("datasets") or []
    repo_ids: list[str] = []
    for item in datasets:
        repo_id = item.get("id") if isinstance(item, dict) else None
        if repo_id and repo_id not in repo_ids:
            repo_ids.append(repo_id)
    return repo_ids


def datasets_missing_hf_url(session: Session) -> list[Dataset]:
    return (
        session.query(Dataset)
        .filter(Dataset.hf_url.is_(None) | (Dataset.hf_url == ""))
        .filter(Dataset.introducing_paper_id.isnot(None))
        .order_by(Dataset.id)
        .all()
    )


def backfill_hf_urls(*, dry_run: bool = True) -> BackfillStats:
    stats = BackfillStats()
    http = requests.Session()

    with db_manager.session_local() as session:
        datasets = datasets_missing_hf_url(session)
        stats.scanned = len(datasets)
        logger.info(
            "Found %d datasets missing hf_url with introducing_paper_id", stats.scanned
        )

        arxiv_cache: dict[str, Optional[list[str]]] = {}
        external_cache: dict[int, list[str]] = {}

        for dataset in datasets:
            if dataset.hf_url:
                stats.skipped_already_set += 1
                continue

            paper = session.get(Paper, dataset.introducing_paper_id)
            if paper is None:
                stats.skipped_no_paper += 1
                logger.info(
                    "Skip dataset %s (%s): introducing paper %s not found",
                    dataset.id,
                    dataset.slug,
                    dataset.introducing_paper_id,
                )
                continue

            repo_ids: Optional[list[str]] = None
            if paper.arxiv_id:
                if paper.arxiv_id not in arxiv_cache:
                    arxiv_cache[paper.arxiv_id] = fetch_hf_dataset_repo_ids(
                        paper.arxiv_id, http
                    )
                repo_ids = arxiv_cache[paper.arxiv_id]
                if repo_ids is None:
                    stats.skipped_api_error += 1
                    continue
            elif paper.hf_datasets:
                if paper.id not in external_cache:
                    external_cache[paper.id] = _repo_ids_from_hf_dataset_urls(
                        paper.hf_datasets
                    )
                repo_ids = external_cache[paper.id]
            else:
                stats.skipped_no_arxiv += 1
                continue

            if not repo_ids:
                stats.skipped_no_hf_datasets += 1
                continue

            hf_url = pick_hf_dataset_url(
                dataset_name=dataset.name,
                dataset_slug=dataset.slug,
                hf_dataset_repo_ids=repo_ids,
            )
            if not hf_url:
                stats.skipped_ambiguous += 1
                logger.info(
                    "Skip dataset %s (%s): ambiguous HF datasets %s",
                    dataset.id,
                    dataset.slug,
                    repo_ids,
                )
                continue

            logger.info(
                "%s dataset %s (%s): hf_url=%s (paper %s)",
                "Would set" if dry_run else "Set",
                dataset.id,
                dataset.slug,
                hf_url,
                paper.arxiv_id or paper.id,
            )
            if not dry_run:
                dataset.hf_url = hf_url
                stats.updated += 1
            else:
                stats.updated += 1

        if not dry_run:
            session.commit()
            logger.info("Committed %d hf_url updates", stats.updated)
        else:
            session.rollback()

    return stats


def _repo_ids_from_hf_dataset_urls(urls: list[str]) -> list[str]:
    """Extract org/name repo ids from stored HF dataset URLs."""
    repo_ids: list[str] = []
    for raw in urls or []:
        marker = "huggingface.co/datasets/"
        if marker not in raw:
            continue
        tail = raw.split(marker, 1)[1].split("?", 1)[0].strip("/")
        if "/" in tail and tail not in repo_ids:
            repo_ids.append(tail)
    return repo_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill datasets.hf_url from source paper HF dataset links"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default is dry-run)",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        logger.warning("DRY RUN — no database changes. Pass --apply to persist.")

    stats = backfill_hf_urls(dry_run=dry_run)
    logger.info("Summary:")
    logger.info("  Scanned:              %d", stats.scanned)
    logger.info("  Proposed/updated:     %d", stats.updated)
    logger.info("  No paper:             %d", stats.skipped_no_paper)
    logger.info("  No arXiv/HF artifacts:%d", stats.skipped_no_arxiv)
    logger.info("  No HF datasets:       %d", stats.skipped_no_hf_datasets)
    logger.info("  Ambiguous:            %d", stats.skipped_ambiguous)
    logger.info("  API errors:           %d", stats.skipped_api_error)


if __name__ == "__main__":
    main()
