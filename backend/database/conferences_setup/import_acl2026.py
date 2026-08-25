#!/usr/bin/env python3
"""Import ACL 2026 papers from ai-conferences/ACL2026 on Hugging Face.

Only rows with an arXiv ID are imported. ACL Anthology-only papers are skipped
because the papers table requires a canonical source identifier.
"""

from __future__ import annotations

import argparse
from datetime import date

from datasets import load_dataset
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.conferences_setup.import_cvpr2026 import link_conference
from backend.models.database import (
    Author,
    Conference,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperTask,
    Task,
)
from backend.utils.keyword_matching import (
    apply_task_supersession_rules,
    create_keyword_patterns,
    find_matching_items_simple,
)

HF_DATASET = "ai-conferences/ACL2026"
PROCEEDING = "ACL 2026"
CONFERENCE_SLUG = "acl-2026"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/ACL2026"
CONFERENCE_DESCRIPTION = (
    "ACL (Annual Meeting of the Association for Computational Linguistics) is a "
    "flagship venue for natural language processing and computational linguistics. "
    "Browse accepted papers from ACL 2026 in San Diego, grouped by research area "
    "and task, with code, project links, evals and Hugging Face artifacts where "
    "available."
)


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    values = {
        "name": PROCEEDING,
        "short_name": "ACL",
        "year": 2026,
        "url": "https://2026.aclweb.org/",
        "start_date": date(2026, 7, 2),
        "end_date": date(2026, 7, 7),
        "venue": "Grand Hyatt Manchester San Diego",
        "location": "San Diego, California, USA",
        "description": CONFERENCE_DESCRIPTION,
        "image_url": None,
        "image_credit": "[ACL 2026](https://2026.aclweb.org/)",
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


def get_or_create_paper(db: Session, row: dict) -> tuple[Paper, bool]:
    arxiv_id = (row.get("arxiv_id") or "").strip()
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


def link_authors(db: Session, paper: Paper, names: list | None) -> int:
    added = 0
    seen: set[str] = set()
    for order, raw_name in enumerate(names or [], start=1):
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

        exists = (
            db.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id,
                PaperAuthor.author_id == author.id,
            )
            .first()
        )
        if exists is None:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    author_id=author.id,
                    author_order=order,
                )
            )
            added += 1
    return added


def load_rows() -> list[dict]:
    dataset = load_dataset(HF_DATASET, split="train")
    return [dict(row) for row in dataset]


def import_rows(
    db: Session, conference: Conference, rows: list[dict]
) -> dict[str, int]:
    stats = {
        "rows": len(rows),
        "skipped_no_arxiv": 0,
        "papers_created": 0,
        "papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
    }
    imported = 0
    for row in rows:
        arxiv_id = (row.get("arxiv_id") or "").strip()
        if not arxiv_id:
            stats["skipped_no_arxiv"] += 1
            continue

        paper, created = get_or_create_paper(db, row)
        stats["papers_created" if created else "papers_updated"] += 1
        stats["authors_added"] += link_authors(db, paper, row.get("authors"))
        if link_conference(db, paper, conference):
            stats["conference_links_added"] += 1

        imported += 1
        if imported % 500 == 0:
            db.commit()
            print(f"  processed {imported} papers with arXiv IDs...")

    db.commit()
    return stats


def link_tasks(db: Session, conference: Conference) -> int:
    tasks = db.query(Task).filter(Task.keywords.is_not(None), Task.keywords != "").all()
    task_rows = [
        {"id": task.id, "slug": task.slug, "keywords": task.keywords} for task in tasks
    ]
    case_sensitive, case_insensitive = create_keyword_patterns(task_rows)
    slug_to_id = {task.slug: task.id for task in tasks}
    task_keywords_by_slug = {
        task.slug: [
            keyword.strip() for keyword in task.keywords.split(",") if keyword.strip()
        ]
        for task in tasks
    }
    papers = (
        db.query(Paper)
        .join(PaperConference, PaperConference.paper_id == Paper.id)
        .filter(PaperConference.conference_id == conference.id)
        .all()
    )

    links: list[dict[str, int | str]] = []
    for paper in papers:
        text = " ".join(part for part in (paper.title, paper.abstract) if part)
        task_ids = find_matching_items_simple(text, case_sensitive, case_insensitive)
        task_ids = apply_task_supersession_rules(
            task_ids,
            slug_to_id,
            text,
            paper.title,
            task_keywords_by_slug,
        )
        links.extend(
            {"paper_id": paper.id, "task_id": task_id, "source": "auto"}
            for task_id in task_ids
        )

    if links:
        statement = insert(PaperTask).values(links)
        db.execute(
            statement.on_conflict_do_nothing(
                index_elements=[PaperTask.paper_id, PaperTask.task_id]
            )
        )
        db.commit()
    return len(links)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ACL 2026 papers")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Loading {HF_DATASET}...")
    rows = load_rows()
    with_arxiv = sum(bool((row.get("arxiv_id") or "").strip()) for row in rows)
    print(
        f"  rows={len(rows)} with_arxiv={with_arxiv} without_arxiv={len(rows) - with_arxiv}"
    )
    if args.dry_run:
        return

    with db_manager.session_local() as db:
        conference = upsert_conference(db)
        print(f"Conference id={conference.id} slug={conference.slug}")
        stats = import_rows(db, conference, rows)
        print("Tagging ACL papers by task keywords (add-only)...")
        stats["task_links_emitted"] = link_tasks(db, conference)

    print("Import complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
