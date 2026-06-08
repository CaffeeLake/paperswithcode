#!/usr/bin/env python3
"""
Import ICCV 2025 papers from ai-conferences/ICCV2025 on Hugging Face.

1. Upserts the ICCV 2025 conference row.
2. Creates missing papers (title, abstract, authors) or updates existing ones.
3. Sets proceeding='ICCV 2025' and CVF conference URLs when present.
4. Links papers to the conference via paper_conferences.
5. Links GitHub repos and project pages when present.
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
from backend.models.database import PaperProjectPage
from backend.models.database import PaperRepository
from backend.models.database import ProjectPage
from backend.models.database import Repository
from backend.services.repository_service import find_repository_by_url
from backend.utils.github_utils import normalize_github_url, parse_github_url

HF_DATASET = "ai-conferences/ICCV2025"
PROCEEDING = "ICCV 2025"
CONFERENCE_SLUG = "iccv-2025"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/ICCV2025"
CONFERENCE_DESCRIPTION = (
    "ICCV (International Conference on Computer Vision) is a premier venue for "
    "computer vision and related machine learning research. Browse accepted papers "
    "from ICCV 2025 in Honolulu, grouped by research area and task, with code, "
    "project links, evals and Hugging Face artifacts where available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(
            name=PROCEEDING,
            slug=CONFERENCE_SLUG,
            short_name="ICCV",
            year=2025,
            url="https://iccv2025.thecvf.com/",
            start_date=date(2025, 10, 19),
            end_date=date(2025, 10, 23),
            venue="Hawaii Convention Center",
            location="Honolulu, USA",
            description=CONFERENCE_DESCRIPTION,
            hf_url=CONFERENCE_HF_URL,
        )
        db.add(conference)
        db.flush()
    else:
        conference.name = PROCEEDING
        conference.short_name = "ICCV"
        conference.year = 2025
        conference.url = "https://iccv2025.thecvf.com/"
        conference.start_date = date(2025, 10, 19)
        conference.end_date = date(2025, 10, 23)
        conference.venue = "Hawaii Convention Center"
        conference.location = "Honolulu, USA"
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

    paper.proceeding = PROCEEDING
    cvf_url = (row.get("cvf_url") or "").strip()
    pdf_url = (row.get("pdf_url") or "").strip()
    if cvf_url:
        paper.conference_url_abs = cvf_url
    if pdf_url:
        paper.conference_url_pdf = pdf_url

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
            source="iccv2025_import",
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


def link_project_page(db: Session, paper: Paper, project_url: str) -> bool:
    url = project_url.strip()
    if not url:
        return False

    page = db.query(ProjectPage).filter(ProjectPage.url == url).first()
    if page is None:
        page = ProjectPage(url=url, is_official=True, source="iccv2025_import")
        db.add(page)
        db.flush()

    link = (
        db.query(PaperProjectPage)
        .filter(
            PaperProjectPage.paper_id == paper.id,
            PaperProjectPage.project_page_id == page.id,
        )
        .first()
    )
    if link is None:
        db.add(PaperProjectPage(paper_id=paper.id, project_page_id=page.id))
        return True
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
        "project_pages_linked": 0,
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

            project_url = (row.get("project_page") or "").strip()
            if project_url and link_project_page(db, paper, project_url):
                stats["project_pages_linked"] += 1

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

    parser = argparse.ArgumentParser(description="Import ICCV 2025 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with/without arxiv_id only; no DB writes",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Importing ICCV 2025 papers" if not args.dry_run else "ICCV 2025 dry run")
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
