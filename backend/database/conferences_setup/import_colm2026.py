#!/usr/bin/env python3
"""Import COLM 2026 papers from ai-conferences/COLM2026."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from datasets import load_dataset
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.database.conferences_setup.import_icml2026 import link_authors_list
from backend.database.connection import db_manager
from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)
from backend.models.database import Conference, Paper

HF_DATASET = "ai-conferences/COLM2026"
PROCEEDING = "COLM 2026"
CONFERENCE_SLUG = "colm-2026"
CONFERENCE_URL = "https://colmweb.org/"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/COLM2026"
CONFERENCE_DESCRIPTION = (
    "COLM (Conference on Language Modeling) is an academic venue focused on "
    "understanding, improving, and critiquing language models across disciplines. "
    "Browse accepted COLM 2026 papers with code, tasks, evaluations, and Hugging "
    "Face artifacts where available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(slug=CONFERENCE_SLUG)
        db.add(conference)

    conference.name = PROCEEDING
    conference.short_name = "COLM"
    conference.year = 2026
    conference.url = CONFERENCE_URL
    conference.start_date = date(2026, 10, 6)
    conference.end_date = date(2026, 10, 9)
    conference.venue = "Hilton San Francisco Union Square"
    conference.location = "San Francisco, California, USA"
    conference.description = CONFERENCE_DESCRIPTION
    conference.image_url = None
    conference.image_credit = f"[COLM 2026]({CONFERENCE_URL})"
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
    if created:
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
    if paper_url:
        paper.conference_url_abs = paper_url
    return paper, created


def load_hf_rows() -> list[dict]:
    print(f"Loading {HF_DATASET} from Hugging Face...")
    dataset = load_dataset(HF_DATASET, split="train")
    print(f"  loaded {len(dataset)} rows")
    return [dict(row) for row in dataset]


def dry_run_stats(rows: list[dict]) -> dict[str, int]:
    with_arxiv = sum(bool((row.get("arxiv_id") or "").strip()) for row in rows)
    return {
        "total_rows": len(rows),
        "with_arxiv_id": with_arxiv,
        "without_arxiv_id": len(rows) - with_arxiv,
    }


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
            with db.begin_nested():
                paper, created = get_or_create_paper(db, row)
                authors_added = link_authors_list(db, paper, row.get("authors"))
                conference_link_added = link_conference(db, paper, conference)
            stats["papers_created" if created else "papers_updated"] += 1
            stats["authors_added"] += authors_added
            stats["conference_links_added"] += conference_link_added
        except (SQLAlchemyError, ValueError) as exc:
            stats["errors"] += 1
            print(f"  error on arxiv_id {arxiv_id}: {exc}")

    db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import COLM 2026 papers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows with/without arxiv_id only; no DB writes",
    )
    args = parser.parse_args()
    rows = load_hf_rows()

    if args.dry_run:
        for key, value in dry_run_stats(rows).items():
            print(f"{key}: {value}")
        return

    session = db_manager.session_local()
    try:
        conference = upsert_conference(session)
        stats = import_dataset(session, conference, rows)
        paper_ids = [paper.id for paper in conference.papers]
        if link_papers_by_task_keywords(rebuild=False, paper_ids=paper_ids):
            raise RuntimeError("Task keyword matching failed")
        for key, value in stats.items():
            print(f"{key}: {value}")
    except (SQLAlchemyError, RuntimeError) as exc:
        session.rollback()
        print(f"Import failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
