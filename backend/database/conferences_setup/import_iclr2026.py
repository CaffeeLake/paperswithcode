#!/usr/bin/env python3
"""
Import ICLR 2026 papers from ai-conferences/ICLR2026 on Hugging Face.

1. Upserts the ICLR 2026 conference row.
2. Creates missing papers (title, abstract, authors) or updates existing ones.
3. Sets proceeding from HF presentation type (oral / poster).
4. Links papers to the conference via paper_conferences.
5. Runs the task keyword matcher (add-only) for auto task tagging.

Only rows with a non-null arxiv_id are imported.
"""

from __future__ import annotations

import sys
from datetime import date

from datasets import load_dataset
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

HF_DATASET = "ai-conferences/ICLR2026"
PROCEEDING = "ICLR 2026"
CONFERENCE_SLUG = "iclr-2026"
CONFERENCE_IMAGE_URL = "https://paperswithcode.co/images/conferences/iclr-2026.png"
CONFERENCE_IMAGE_CREDIT = "[ICLR 2026](https://iclr.cc/Conferences/2026)"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/ICLR2026"
CONFERENCE_DESCRIPTION = (
    "ICLR (International Conference on Learning Representations) is a premier "
    "venue for deep learning and representation learning research. Browse "
    "accepted papers from ICLR 2026 in Rio de Janeiro, grouped by research area "
    "and task, with code, project links, evals and Hugging Face artifacts "
    "where available."
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
            short_name="ICLR",
            year=2026,
            url="https://iclr.cc/Conferences/2026",
            start_date=date(2026, 4, 23),
            end_date=date(2026, 4, 27),
            venue="Riocentro Convention and Event Center",
            location="Rio de Janeiro, Brazil",
            description=CONFERENCE_DESCRIPTION,
            image_url=CONFERENCE_IMAGE_URL,
            image_credit=CONFERENCE_IMAGE_CREDIT,
            hf_url=CONFERENCE_HF_URL,
        )
        db.add(conference)
        db.flush()
    else:
        conference.name = PROCEEDING
        conference.short_name = "ICLR"
        conference.year = 2026
        conference.url = "https://iclr.cc/Conferences/2026"
        conference.start_date = date(2026, 4, 23)
        conference.end_date = date(2026, 4, 27)
        conference.venue = "Riocentro Convention and Event Center"
        conference.location = "Rio de Janeiro, Brazil"
        conference.description = CONFERENCE_DESCRIPTION
        conference.image_url = CONFERENCE_IMAGE_URL
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

    parser = argparse.ArgumentParser(description="Import ICLR 2026 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with/without arxiv_id only; no DB writes",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Importing ICLR 2026 papers" if not args.dry_run else "ICLR 2026 dry run")
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
