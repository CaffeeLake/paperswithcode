#!/usr/bin/env python3
"""Import AAAI 2026 papers from ai-conferences/AAAI2026 on Hugging Face.

The importer upserts the conference metadata, creates or updates papers that
have an arXiv identifier, links authors and proceedings URLs, associates the
papers with AAAI 2026, and runs the add-only task keyword matcher.

Rows without an arXiv identifier are reported but not imported because the
papers table uses arXiv identity for this conference-import workflow.
"""

from __future__ import annotations

import argparse
from datetime import date

from datasets import load_dataset
from sqlalchemy.orm import Session

from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.database.connection import db_manager
from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)
from backend.models.database import Author, Conference, Paper, PaperAuthor

HF_DATASET = "ai-conferences/AAAI2026"
PROCEEDING = "AAAI 2026"
CONFERENCE_SLUG = "aaai-2026"
CONFERENCE_URL = "https://aaai.org/conference/aaai/aaai-26/"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/AAAI2026"
CONFERENCE_IMAGE_CREDIT = f"[AAAI 2026]({CONFERENCE_URL})"
CONFERENCE_DESCRIPTION = (
    "AAAI (Association for the Advancement of Artificial Intelligence) is a "
    "leading venue spanning the breadth of artificial intelligence research. "
    "Browse papers from AAAI 2026 in Singapore, grouped by research area and "
    "task, with code, project links, evaluations, and Hugging Face artifacts "
    "where available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(slug=CONFERENCE_SLUG)
        db.add(conference)

    conference.name = PROCEEDING
    conference.short_name = "AAAI"
    conference.year = 2026
    conference.url = CONFERENCE_URL
    conference.start_date = date(2026, 1, 20)
    conference.end_date = date(2026, 1, 27)
    conference.venue = "Singapore EXPO"
    conference.location = "Singapore, Singapore"
    conference.description = CONFERENCE_DESCRIPTION
    conference.image_url = None
    conference.image_credit = CONFERENCE_IMAGE_CREDIT
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
    created = paper is None
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

    paper.proceeding = PROCEEDING
    paper_url = (row.get("paper_url") or "").strip()
    pdf_url = (row.get("pdf_url") or "").strip()
    if paper_url:
        paper.conference_url_abs = paper_url
    if pdf_url:
        paper.conference_url_pdf = pdf_url

    return paper, created


def link_authors(db: Session, paper: Paper, authors: list | None) -> int:
    added = 0
    seen: set[str] = set()
    for order, raw_name in enumerate(authors or [], start=1):
        name = str(raw_name).strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)

        author = db.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            db.add(author)
            db.flush()

        existing = (
            db.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id,
                PaperAuthor.author_id == author.id,
            )
            .first()
        )
        if existing is None:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    author_id=author.id,
                    author_order=order,
                )
            )
            added += 1

    return added


def load_hf_rows() -> list[dict]:
    print(f"Loading {HF_DATASET} from Hugging Face...")
    dataset = load_dataset(HF_DATASET, "default", split="train")
    print(f"  loaded {len(dataset)} rows")
    return [dict(row) for row in dataset]


def dry_run_stats(rows: list[dict]) -> dict[str, int]:
    with_arxiv_id = sum(bool((row.get("arxiv_id") or "").strip()) for row in rows)
    return {
        "total_rows": len(rows),
        "with_arxiv_id": with_arxiv_id,
        "without_arxiv_id": len(rows) - with_arxiv_id,
    }


def import_dataset(
    db: Session, conference: Conference, rows: list[dict]
) -> tuple[dict[str, int], list[int]]:
    stats = {
        "rows": len(rows),
        "skipped_no_arxiv": 0,
        "papers_created": 0,
        "papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
    }
    paper_ids: list[int] = []

    imported = 0
    for row in rows:
        if not (row.get("arxiv_id") or "").strip():
            stats["skipped_no_arxiv"] += 1
            continue

        paper, created = get_or_create_paper(db, row)
        paper_ids.append(paper.id)
        stats["papers_created" if created else "papers_updated"] += 1
        stats["authors_added"] += link_authors(db, paper, row.get("authors"))
        if link_conference(db, paper, conference):
            stats["conference_links_added"] += 1

        imported += 1
        if imported % 500 == 0:
            db.commit()
            print(f"  processed {imported} papers with arxiv_id...")

    db.commit()
    return stats, paper_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Import AAAI 2026 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with and without arXiv IDs; do not write to the database",
    )
    args = parser.parse_args()

    rows = load_hf_rows()
    if args.dry_run:
        for key, value in dry_run_stats(rows).items():
            print(f"{key}: {value}")
        return

    with db_manager.session_local() as db:
        conference = upsert_conference(db)
        print(f"Conference id={conference.id} slug={conference.slug}")
        stats, paper_ids = import_dataset(db, conference, rows)

    print("Running task keyword matcher (add-only)...")
    link_papers_by_task_keywords(rebuild=False, paper_ids=paper_ids)

    print("Import complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
