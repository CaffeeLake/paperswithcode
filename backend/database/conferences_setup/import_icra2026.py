#!/usr/bin/env python3
"""
Import ICRA 2026 papers from ai-conferences/ICRA2026 on Hugging Face.

1. Upserts the ICRA 2026 conference row.
2. Creates or updates arXiv papers when arxiv_id is present.
3. Creates or updates external papers when arxiv_id is missing (source_url = program_url).
4. Sets proceeding='ICRA 2026' and conference program URLs.
5. Links papers to the conference via paper_conferences.
6. Runs the task keyword matcher (add-only) for auto task tagging.
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

HF_DATASET = "ai-conferences/ICRA2026"
PROCEEDING = "ICRA 2026"
CONFERENCE_SLUG = "icra-2026"
CONFERENCE_IMAGE_URL = "https://paperswithcode.co/images/conferences/icra-2026.png"
CONFERENCE_IMAGE_CREDIT = "[ICRA 2026](https://2026.ieee-icra.org/)"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/ICRA2026"
CONFERENCE_DESCRIPTION = (
    "ICRA (IEEE International Conference on Robotics and Automation) is the "
    "flagship conference of the IEEE Robotics and Automation Society. Browse "
    "accepted papers from ICRA 2026 in Vienna, grouped by research area and "
    "task, with code, project links, evals and Hugging Face artifacts where "
    "available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(
            name=PROCEEDING,
            slug=CONFERENCE_SLUG,
            short_name="ICRA",
            year=2026,
            url="https://2026.ieee-icra.org/",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            venue="VIECON – Vienna Congress & Convention Center",
            location="Vienna, Austria",
            description=CONFERENCE_DESCRIPTION,
            image_url=CONFERENCE_IMAGE_URL,
            image_credit=CONFERENCE_IMAGE_CREDIT,
            hf_url=CONFERENCE_HF_URL,
        )
        db.add(conference)
        db.flush()
    else:
        conference.name = PROCEEDING
        conference.short_name = "ICRA"
        conference.year = 2026
        conference.url = "https://2026.ieee-icra.org/"
        conference.start_date = date(2026, 6, 1)
        conference.end_date = date(2026, 6, 5)
        conference.venue = "VIECON – Vienna Congress & Convention Center"
        conference.location = "Vienna, Austria"
        conference.description = CONFERENCE_DESCRIPTION
        conference.image_url = CONFERENCE_IMAGE_URL
        conference.image_credit = CONFERENCE_IMAGE_CREDIT
        conference.hf_url = CONFERENCE_HF_URL
    db.commit()
    db.refresh(conference)
    return conference


def _program_url(row: dict) -> str:
    return (row.get("program_url") or "").strip()


def get_or_create_arxiv_paper(db: Session, row: dict) -> tuple[Paper, bool]:
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
    program_url = _program_url(row)
    if program_url:
        paper.conference_url_abs = program_url

    return paper, created


def get_or_create_external_paper(db: Session, row: dict) -> tuple[Paper, bool]:
    program_url = _program_url(row)
    if not program_url:
        raise ValueError("Missing program_url for external paper")

    paper = (
        db.query(Paper)
        .filter(Paper.source_url == program_url, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    created = False
    if paper is None:
        paper = Paper(
            title=(row.get("title") or "").strip(),
            abstract=(row.get("abstract") or "").strip() or None,
            source="external",
            source_url=program_url,
            version="v1",
            is_latest_version=True,
            proceeding=PROCEEDING,
            conference_url_abs=program_url,
        )
        db.add(paper)
        db.flush()
        created = True
    else:
        paper.proceeding = PROCEEDING
        paper.conference_url_abs = program_url

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
        "without_arxiv_missing_program_url": 0,
    }
    for row in rows:
        arxiv_id = (row.get("arxiv_id") or "").strip()
        if arxiv_id:
            stats["with_arxiv_id"] += 1
            continue
        stats["without_arxiv_id"] += 1
        if not _program_url(row):
            stats["without_arxiv_missing_program_url"] += 1
    return stats


def import_dataset(
    db: Session, conference: Conference, rows: list[dict]
) -> dict[str, int]:
    stats = {
        "rows": 0,
        "skipped_no_identifier": 0,
        "arxiv_papers_created": 0,
        "arxiv_papers_updated": 0,
        "external_papers_created": 0,
        "external_papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
        "errors": 0,
    }

    for row in rows:
        stats["rows"] += 1
        arxiv_id = (row.get("arxiv_id") or "").strip()
        program_url = _program_url(row)

        if not arxiv_id and not program_url:
            stats["skipped_no_identifier"] += 1
            continue

        try:
            if arxiv_id:
                paper, created = get_or_create_arxiv_paper(db, row)
                if created:
                    stats["arxiv_papers_created"] += 1
                else:
                    stats["arxiv_papers_updated"] += 1
            else:
                paper, created = get_or_create_external_paper(db, row)
                if created:
                    stats["external_papers_created"] += 1
                else:
                    stats["external_papers_updated"] += 1

            stats["authors_added"] += link_authors_list(db, paper, row.get("authors"))

            if link_conference(db, paper, conference):
                stats["conference_links_added"] += 1

            imported = (
                stats["arxiv_papers_created"]
                + stats["arxiv_papers_updated"]
                + stats["external_papers_created"]
                + stats["external_papers_updated"]
            )
            if imported % 500 == 0:
                db.commit()
                print(f"  processed {imported} papers...")
        except Exception as exc:
            stats["errors"] += 1
            label = arxiv_id or program_url
            print(f"  error on {label}: {exc}")

    db.commit()
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import ICRA 2026 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with/without arxiv_id only; no DB writes",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Importing ICRA 2026 papers" if not args.dry_run else "ICRA 2026 dry run")
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
