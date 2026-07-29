#!/usr/bin/env python3
"""Import MICCAI 2025 papers from ai-conferences/MICCAI2025."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from datasets import load_dataset
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.database.connection import db_manager
from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)
from backend.models.database import (
    Author,
    Conference,
    Paper,
    PaperAuthor,
    PaperProjectPage,
    PaperRepository,
    ProjectPage,
    Repository,
)
from backend.services.repository_service import find_repository_by_url
from backend.utils.github_utils import normalize_github_url, parse_github_url

HF_DATASET = "ai-conferences/MICCAI2025"
PROCEEDING = "MICCAI 2025"
CONFERENCE_SLUG = "miccai-2025"
CONFERENCE_URL = "https://conferences.miccai.org/2025/en/"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/MICCAI2025"
CONFERENCE_IMAGE_CREDIT = f"[MICCAI 2025]({CONFERENCE_URL})"
CONFERENCE_DESCRIPTION = (
    "MICCAI (International Conference on Medical Image Computing and Computer "
    "Assisted Intervention) is a leading venue for medical imaging, "
    "computer-assisted intervention, and related machine learning research. "
    "Browse accepted papers from MICCAI 2025 in Daejeon, grouped by research "
    "area and task, with code, project links, evals and Hugging Face artifacts "
    "where available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    values = {
        "name": PROCEEDING,
        "short_name": "MICCAI",
        "year": 2025,
        "url": CONFERENCE_URL,
        "start_date": date(2025, 9, 23),
        "end_date": date(2025, 9, 27),
        "venue": "Daejeon Convention Center",
        "location": "Daejeon, South Korea",
        "description": CONFERENCE_DESCRIPTION,
        "image_url": None,
        "image_credit": CONFERENCE_IMAGE_CREDIT,
        "hf_url": CONFERENCE_HF_URL,
    }
    if conference is None:
        conference = Conference(slug=CONFERENCE_SLUG, **values)
        db.add(conference)
    else:
        for field, value in values.items():
            setattr(conference, field, value)
    db.commit()
    db.refresh(conference)
    return conference


def _miccai_url(row: dict) -> str:
    return (row.get("miccai_url") or "").strip()


def _set_conference_fields(paper: Paper, row: dict) -> None:
    paper.proceeding = PROCEEDING
    miccai_url = _miccai_url(row)
    pdf_url = (row.get("pdf_url") or "").strip()
    if miccai_url:
        paper.conference_url_abs = miccai_url
    if pdf_url:
        paper.conference_url_pdf = pdf_url


def get_or_create_paper(db: Session, row: dict) -> tuple[Paper, bool, bool]:
    arxiv_id = (row.get("arxiv_id") or "").strip()
    miccai_url = _miccai_url(row)
    created = False

    if arxiv_id:
        paper = (
            db.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
            .order_by(Paper.id.desc())
            .first()
        )
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
        _set_conference_fields(paper, row)
        return paper, created, True

    if not miccai_url:
        raise ValueError("Missing arxiv_id and miccai_url")

    paper = (
        db.query(Paper)
        .filter(Paper.source_url == miccai_url, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is None:
        paper = Paper(
            title=(row.get("title") or "").strip(),
            abstract=(row.get("abstract") or "").strip() or None,
            source="external",
            source_url=miccai_url,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        created = True
    else:
        paper.title = (row.get("title") or "").strip()
        paper.abstract = (row.get("abstract") or "").strip() or None
    _set_conference_fields(paper, row)
    return paper, created, False


def link_authors(db: Session, paper: Paper, authors: list | None) -> int:
    added = 0
    seen: set[str] = set()
    for order, raw_name in enumerate(authors or [], start=1):
        name = str(raw_name).strip()
        key = name.lower()
        if not name or key in seen:
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


def link_github_repository(db: Session, paper: Paper, url: str) -> bool:
    normalized = normalize_github_url(url.strip())
    if not normalized:
        return False

    owner, name = parse_github_url(normalized)
    repository = find_repository_by_url(db, normalized)
    if repository is None:
        repository = Repository(
            url=normalized,
            owner=owner,
            name=name,
            num_stars=0,
            source="miccai2025_import",
        )
        db.add(repository)
        db.flush()
    elif repository.url != normalized:
        repository.url = normalized
        repository.owner = repository.owner or owner
        repository.name = repository.name or name

    variant_links = (
        db.query(PaperRepository)
        .join(Repository, Repository.id == PaperRepository.repository_id)
        .filter(
            PaperRepository.paper_id == paper.id,
            func.lower(Repository.url) == normalized.lower(),
            PaperRepository.repository_id != repository.id,
        )
        .all()
    )
    for variant_link in variant_links:
        db.delete(variant_link)

    link = (
        db.query(PaperRepository)
        .filter(
            PaperRepository.paper_id == paper.id,
            PaperRepository.repository_id == repository.id,
        )
        .first()
    )
    if link is None:
        db.add(
            PaperRepository(
                paper_id=paper.id,
                repository_id=repository.id,
                is_official=True,
            )
        )
        return True
    link.is_official = True
    return False


def link_project_page(db: Session, paper: Paper, url: str) -> bool:
    normalized = url.strip()
    if not normalized:
        return False

    page = db.query(ProjectPage).filter(ProjectPage.url == normalized).first()
    if page is None:
        page = ProjectPage(
            url=normalized,
            is_official=True,
            source="miccai2025_import",
        )
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
        db.add(
            PaperProjectPage(
                paper_id=paper.id,
                project_page_id=page.id,
            )
        )
        return True
    return False


def link_code_urls(db: Session, paper: Paper, urls: list | None) -> tuple[int, int]:
    repositories_added = 0
    project_pages_added = 0
    for url in dict.fromkeys(urls or []):
        hostname = urlparse(url).hostname or ""
        if hostname.lower() in {"github.com", "www.github.com"}:
            repositories_added += link_github_repository(db, paper, url)
        else:
            project_pages_added += link_project_page(db, paper, url)
    return repositories_added, project_pages_added


def load_hf_rows() -> list[dict]:
    print(f"Loading {HF_DATASET} from Hugging Face...")
    dataset = load_dataset(HF_DATASET, split="train")
    print(f"  loaded {len(dataset)} rows")
    return [dict(row) for row in dataset]


def dry_run_stats(rows: list[dict]) -> dict[str, int]:
    return {
        "total_rows": len(rows),
        "with_arxiv_id": sum(bool((row.get("arxiv_id") or "").strip()) for row in rows),
        "without_arxiv_id": sum(
            not bool((row.get("arxiv_id") or "").strip()) for row in rows
        ),
        "without_identifier": sum(
            not (row.get("arxiv_id") or "").strip() and not _miccai_url(row)
            for row in rows
        ),
    }


def import_dataset(
    db: Session, conference: Conference, rows: list[dict]
) -> tuple[dict[str, int], list[int]]:
    stats = {
        "rows": 0,
        "skipped_no_identifier": 0,
        "arxiv_papers_created": 0,
        "arxiv_papers_updated": 0,
        "external_papers_created": 0,
        "external_papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
        "repositories_linked": 0,
        "project_pages_linked": 0,
    }
    paper_ids: list[int] = []

    for row in rows:
        stats["rows"] += 1
        if not (row.get("arxiv_id") or "").strip() and not _miccai_url(row):
            stats["skipped_no_identifier"] += 1
            continue

        paper, created, is_arxiv = get_or_create_paper(db, row)
        paper_ids.append(paper.id)
        paper_type = "arxiv" if is_arxiv else "external"
        result = "created" if created else "updated"
        stats[f"{paper_type}_papers_{result}"] += 1
        stats["authors_added"] += link_authors(db, paper, row.get("authors"))

        repositories, project_pages = link_code_urls(db, paper, row.get("code_urls"))
        stats["repositories_linked"] += repositories
        stats["project_pages_linked"] += project_pages

        if link_conference(db, paper, conference):
            stats["conference_links_added"] += 1

        imported = stats["arxiv_papers_created"] + stats["arxiv_papers_updated"]
        imported += stats["external_papers_created"] + stats["external_papers_updated"]
        if imported % 500 == 0:
            db.commit()
            print(f"  processed {imported} papers...")

    db.commit()
    return stats, paper_ids


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import MICCAI 2025 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows by identifier type; no DB writes",
    )
    args = parser.parse_args()

    rows = load_hf_rows()
    if args.dry_run:
        print("Dry run complete:")
        for key, value in dry_run_stats(rows).items():
            print(f"  {key}: {value}")
        return

    session = db_manager.session_local()
    try:
        print("1. Upserting conference row...")
        conference = upsert_conference(session)
        print(f"   conference id={conference.id} slug={conference.slug}")

        print("2. Importing papers from Hugging Face dataset...")
        stats, paper_ids = import_dataset(session, conference, rows)

        print("3. Running task keyword matcher for imported papers (add-only)...")
        link_papers_by_task_keywords(rebuild=False, paper_ids=paper_ids)

        print("Import complete:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
