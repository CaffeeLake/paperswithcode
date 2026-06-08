#!/usr/bin/env python3
"""
Import ICML 2025 papers from ai-conferences/ICML2025 on Hugging Face.

1. Upserts the ICML 2025 conference row.
2. Creates missing papers (title, abstract, authors) or updates existing ones.
3. Sets proceeding from HF presentation type (oral / spotlight / poster).
4. Links papers to the conference via paper_conferences.
5. Links GitHub repos when present.
6. Runs the task keyword matcher (add-only) for auto task tagging.

Only rows with a non-null arxiv_id are imported.
"""

from __future__ import annotations

import sys
from datetime import date

from datasets import load_dataset
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)
from backend.models.database import Author
from backend.models.database import Conference
from backend.models.database import Paper
from backend.models.database import PaperAuthor
from backend.models.database import PaperRepository
from backend.models.database import Repository
from backend.services.repository_service import find_repository_by_url
from backend.utils.github_utils import normalize_github_url, parse_github_url

HF_DATASET = "ai-conferences/ICML2025"
PROCEEDING = "ICML 2025"
CONFERENCE_SLUG = "icml-2025"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/ICML2025"
CONFERENCE_DESCRIPTION = (
    "ICML (International Conference on Machine Learning) is a leading venue for "
    "machine learning research. Browse accepted papers from ICML 2025 in Vancouver, "
    "grouped by research area and task, with code, project links, evals and Hugging "
    "Face artifacts where available."
)


def proceeding_for_type(presentation_type: str | None) -> str:
    normalized = (presentation_type or "").strip().lower()
    if normalized == "oral":
        return f"{PROCEEDING} Oral"
    if normalized == "spotlight":
        return f"{PROCEEDING} Spotlight"
    return PROCEEDING


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(
            name=PROCEEDING,
            slug=CONFERENCE_SLUG,
            short_name="ICML",
            year=2025,
            url="https://icml.cc/Conferences/2025",
            start_date=date(2025, 7, 13),
            end_date=date(2025, 7, 19),
            venue="Vancouver Convention Centre",
            location="Vancouver, Canada",
            description=CONFERENCE_DESCRIPTION,
            hf_url=CONFERENCE_HF_URL,
        )
        db.add(conference)
        db.flush()
    else:
        conference.name = PROCEEDING
        conference.short_name = "ICML"
        conference.year = 2025
        conference.url = "https://icml.cc/Conferences/2025"
        conference.start_date = date(2025, 7, 13)
        conference.end_date = date(2025, 7, 19)
        conference.venue = "Vancouver Convention Centre"
        conference.location = "Vancouver, Canada"
        conference.description = CONFERENCE_DESCRIPTION
        conference.hf_url = CONFERENCE_HF_URL
    db.commit()
    db.refresh(conference)
    return conference


def get_or_create_paper(db: Session, row: dict) -> tuple[Paper, bool]:
    arxiv_id = (row.get("arxiv_id") or "").strip()
    if not arxiv_id:
        raise ValueError("Missing arxiv_id")

    paper = (
        db.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    created = False
    if paper is None:
        paper = Paper(
            arxiv_id=arxiv_id,
            title=(row.get("title") or "").strip(),
            abstract=(row.get("abstract") or "").strip() or None,
            version="v1",
            is_latest_version=True,
            source="arxiv",
        )
        db.add(paper)
        db.flush()
        created = True

    paper.proceeding = proceeding_for_type(row.get("type"))
    paper_url = (row.get("paper_url") or "").strip()
    if paper_url:
        paper.conference_url_abs = paper_url

    return paper, created


def link_authors_list(db: Session, paper: Paper, authors: list | None) -> int:
    if not authors:
        return 0

    added = 0
    seen: set[str] = set()
    for order, raw_name in enumerate(authors, start=1):
        name = str(raw_name).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        author = db.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            db.add(author)
            db.flush()

        link = (
            db.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id,
                PaperAuthor.author_id == author.id,
            )
            .first()
        )
        if link is None:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    author_id=author.id,
                    author_order=order,
                )
            )
            added += 1

    return added


def link_github_repo(db: Session, paper: Paper, github_url: str) -> bool:
    normalized = normalize_github_url(github_url.strip())
    if not normalized:
        return False

    owner, name = parse_github_url(normalized)
    repo = find_repository_by_url(db, normalized)
    if repo is None:
        repo = Repository(
            url=normalized,
            owner=owner,
            name=name,
            num_stars=0,
            source="icml2025_import",
        )
        db.add(repo)
        db.flush()
    elif repo.url != normalized:
        repo.url = normalized
        repo.owner = repo.owner or owner
        repo.name = repo.name or name

    variant_links = (
        db.query(PaperRepository)
        .join(Repository, Repository.id == PaperRepository.repository_id)
        .filter(
            PaperRepository.paper_id == paper.id,
            func.lower(Repository.url) == normalized.lower(),
            PaperRepository.repository_id != repo.id,
        )
        .all()
    )
    for variant_link in variant_links:
        db.delete(variant_link)

    link = (
        db.query(PaperRepository)
        .filter(
            PaperRepository.paper_id == paper.id,
            PaperRepository.repository_id == repo.id,
        )
        .first()
    )
    if link is None:
        db.add(
            PaperRepository(
                paper_id=paper.id,
                repository_id=repo.id,
                is_official=True,
            )
        )
        return True
    if not link.is_official:
        link.is_official = True
    return False


def load_hf_rows() -> list[dict]:
    print(f"Loading {HF_DATASET} from Hugging Face...")
    dataset = load_dataset(HF_DATASET, split="train")
    print(f"  loaded {len(dataset)} rows")
    return [dict(row) for row in dataset]


def dry_run_stats(rows: list[dict]) -> dict[str, int]:
    stats = {
        "total_rows": len(rows),
        "with_arxiv_id": 0,
        "without_arxiv_id": 0,
    }
    for row in rows:
        arxiv_id = (row.get("arxiv_id") or "").strip()
        if arxiv_id:
            stats["with_arxiv_id"] += 1
        else:
            stats["without_arxiv_id"] += 1
    return stats


def import_dataset(
    db: Session, conference: Conference, rows: list[dict]
) -> dict[str, int]:
    stats = {
        "rows": 0,
        "skipped_no_arxiv": 0,
        "papers_created": 0,
        "papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
        "repos_linked": 0,
        "errors": 0,
    }

    for row in rows:
        stats["rows"] += 1
        arxiv_id = (row.get("arxiv_id") or "").strip()
        if not arxiv_id:
            stats["skipped_no_arxiv"] += 1
            continue

        try:
            paper, created = get_or_create_paper(db, row)
            if created:
                stats["papers_created"] += 1
            else:
                stats["papers_updated"] += 1

            stats["authors_added"] += link_authors_list(db, paper, row.get("authors"))

            github_url = (row.get("github") or "").strip()
            if github_url and link_github_repo(db, paper, github_url):
                stats["repos_linked"] += 1

            if link_conference(db, paper, conference):
                stats["conference_links_added"] += 1

            imported = stats["papers_created"] + stats["papers_updated"]
            if imported % 500 == 0:
                db.commit()
                print(f"  processed {imported} papers with arxiv_id...")
        except Exception as exc:
            stats["errors"] += 1
            print(f"  error on arxiv_id {arxiv_id}: {exc}")

    db.commit()
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import ICML 2025 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with/without arxiv_id only; no DB writes",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Importing ICML 2025 papers" if not args.dry_run else "ICML 2025 dry run")
    print("=" * 80)

    rows = load_hf_rows()

    if args.dry_run:
        stats = dry_run_stats(rows)
        print("\nDry run complete:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return

    session = db_manager.session_local()
    try:
        print("\n1. Upserting conference row...")
        conference = upsert_conference(session)
        print(f"   conference id={conference.id} slug={conference.slug}")

        print("\n2. Importing papers from Hugging Face dataset...")
        stats = import_dataset(session, conference, rows)

        print("\n3. Running task keyword matcher (add-only)...")
        link_papers_by_task_keywords(rebuild=False)

        print("\n" + "=" * 80)
        print("Import complete")
        print("=" * 80)
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        session.rollback()
        print(f"Import failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
