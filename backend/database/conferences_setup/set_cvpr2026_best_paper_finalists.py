#!/usr/bin/env python3
"""
Set CVPR 2026 best-paper-finalist awards on paper_conferences rows.

Source: CVPR 2026 Best Paper Finalists slide (including winners).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from backend.database.connection import db_manager
from backend.database.paper_merge import merge_external_paper_into_arxiv
from backend.database.scrape_cvpr2026_papers import normalize_title
from backend.models.database import (
    Author,
    Conference,
    Paper,
    PaperAuthor,
    PaperConference,
)

CONFERENCE_SLUG = "cvpr-2026"
PROCEEDING = "CVPR 2026"
FINALIST_PROCEEDING = "CVPR 2026 Best Paper Finalist"
AWARD = "best_paper_finalist"
CSV_PATH = Path(__file__).resolve().parents[3] / "data" / "cvpr2026_papers.csv"

FINALIST_TITLES = [
    "Mapping Networks",
    "VGGT-Ω",
    "Towards Photorealistic and Efficient Bokeh Rendering via Diffusion Framework",
    "Efficiently Reconstructing Dynamic Scenes One D4RT at a Time",
    "PixelDiT: Pixel Diffusion Transformers for Image Generation",
    "NuWa: Deriving Lightweight Class-Specific Vision Transformers for Edge Devices",
    "ViT$^3$: Unlocking Test-Time Training in Vision",
    "Black-box Membership Inference Attacks on the Pre-training Data of Image-generation Models",
    "SAM 3D: 3Dfy Anything in Images",
    "3DReflecNet: A Large-Scale Dataset for 3D Reconstruction of Reflective, Transparent, and Low-Texture Objects",
    "Rethinking Dataset Distillation: Hard Truths about Soft Labels",
    "Native and Compact Structured Latents for 3D Generation",
    "SeaCache: Spectral-Evolution-Aware Cache for Accelerating Diffusion Models",
    "NitroGen: An Open Foundation Model for Generalist Gaming Agents",
    "ChordEdit: One-Step Low-Energy Transport for Image Editing",
]

# Slide titles that do not normalize to our stored arXiv titles (e.g. LaTeX Ω).
FINALIST_ARXIV_BY_TITLE: dict[str, str] = {
    "VGGT-Ω": "2605.15195",
}

FINALIST_CVF_HTML_BY_ARXIV: dict[str, str] = {
    "2605.15195": "https://cvpr.thecvf.com/virtual/2026/oral/40381",
}


def _csv_row_by_title(title: str) -> dict[str, str] | None:
    key = normalize_title(title)
    with CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if normalize_title(row.get("title") or "") == key:
                return row
    return None


def _link_authors(session, paper: Paper, authors_str: str) -> None:
    for order, raw_name in enumerate(authors_str.split(";"), start=1):
        name = raw_name.strip()
        if not name:
            continue
        author = session.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            session.add(author)
            session.flush()
        link = (
            session.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id,
                PaperAuthor.author_id == author.id,
            )
            .first()
        )
        if link is None:
            session.add(
                PaperAuthor(
                    paper_id=paper.id,
                    author_id=author.id,
                    author_order=order,
                )
            )


def _ensure_conference_link(
    session, paper: Paper, conference: Conference
) -> PaperConference:
    link = (
        session.query(PaperConference)
        .filter(
            PaperConference.paper_id == paper.id,
            PaperConference.conference_id == conference.id,
        )
        .first()
    )
    if link is None:
        link = PaperConference(
            paper_id=paper.id,
            conference_id=conference.id,
            source="manual",
        )
        session.add(link)
        session.flush()
    return link


def _get_or_create_arxiv_paper(
    session, row: dict[str, str], *, seed_authors: bool = True
) -> tuple[Paper, bool]:
    arxiv_id = (row.get("arxiv_id") or "").strip()
    if not arxiv_id:
        raise ValueError("Missing arxiv_id")

    paper = (
        session.query(Paper)
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
        session.add(paper)
        session.flush()
        created = True
        if seed_authors:
            _link_authors(session, paper, row.get("authors") or "")

    cvf_html = (row.get("cvf_html_url") or "").strip()
    pdf_url = (row.get("pdf_url") or "").strip()
    paper.proceeding = PROCEEDING
    if cvf_html:
        paper.conference_url_abs = cvf_html
    if pdf_url:
        paper.conference_url_pdf = pdf_url

    return paper, created


def _find_external_by_cvf(session, cvf_html: str) -> Paper | None:
    if not cvf_html:
        return None
    return (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == cvf_html,
            Paper.is_latest_version,
        )
        .order_by(Paper.id.asc())
        .first()
    )


def _merge_external_duplicate(session, arxiv_paper: Paper, cvf_html: str) -> None:
    external = _find_external_by_cvf(session, cvf_html)
    if external is None or external.id == arxiv_paper.id:
        return
    merge_external_paper_into_arxiv(session, external.id, arxiv_paper.id)


def _ensure_paper_from_csv(session, conference: Conference, title: str) -> Paper | None:
    row = _csv_row_by_title(title)
    if row is None:
        return None

    arxiv_id = (row.get("arxiv_id") or "").strip()
    if arxiv_id:
        cvf_html = (row.get("cvf_html_url") or "").strip()
        has_external = _find_external_by_cvf(session, cvf_html) is not None
        paper, created = _get_or_create_arxiv_paper(
            session, row, seed_authors=not has_external
        )
        _merge_external_duplicate(session, paper, cvf_html)
        _ensure_conference_link(session, paper, conference)
        return paper

    cvf_html = (row.get("cvf_html_url") or "").strip()
    if not cvf_html:
        return None

    paper = (
        session.query(Paper)
        .filter(Paper.source_url == cvf_html, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is None:
        paper = Paper(
            title=(row.get("title") or title).strip(),
            abstract=(row.get("abstract") or "").strip() or None,
            source="external",
            source_url=cvf_html,
            version="v1",
            is_latest_version=True,
            proceeding=PROCEEDING,
            conference_url_abs=cvf_html,
            conference_url_pdf=(row.get("pdf_url") or "").strip() or None,
        )
        session.add(paper)
        session.flush()
        _link_authors(session, paper, row.get("authors") or "")

    _ensure_conference_link(session, paper, conference)
    return paper


def _ensure_paper_by_arxiv(
    session, conference: Conference, arxiv_id: str, *, cvf_html: str | None = None
) -> Paper | None:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is None:
        return None

    paper.proceeding = PROCEEDING
    if cvf_html:
        paper.conference_url_abs = cvf_html
    _ensure_conference_link(session, paper, conference)
    return paper


def main() -> None:
    session = db_manager.session_local()
    try:
        conference = (
            session.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
        )
        if conference is None:
            print(f"Conference not found: {CONFERENCE_SLUG}")
            sys.exit(1)

        paper_rows = (
            session.query(Paper, PaperConference)
            .join(
                PaperConference,
                Paper.id == PaperConference.paper_id,
            )
            .filter(
                PaperConference.conference_id == conference.id,
                Paper.is_latest_version,
            )
            .all()
        )

        title_to_link: dict[str, tuple[Paper, PaperConference]] = {}
        for paper, link in paper_rows:
            title_to_link[normalize_title(paper.title)] = (paper, link)

        updated = 0
        missing: list[str] = []
        finalist_paper_ids: set[int] = set()
        for title in FINALIST_TITLES:
            arxiv_override = FINALIST_ARXIV_BY_TITLE.get(title)
            if arxiv_override:
                cvf_html = FINALIST_CVF_HTML_BY_ARXIV.get(arxiv_override)
                paper = _ensure_paper_by_arxiv(
                    session, conference, arxiv_override, cvf_html=cvf_html
                )
                if paper is None:
                    print(f"  missing paper: {title} ({arxiv_override})")
                    missing.append(title)
                    continue
                link = _ensure_conference_link(session, paper, conference)
                link.award = AWARD
                paper.proceeding = FINALIST_PROCEEDING
                finalist_paper_ids.add(paper.id)
                updated += 1
                print(f"  {paper.arxiv_id} {paper.title} -> {AWARD}")
                continue

            key = normalize_title(title)
            match = title_to_link.get(key)
            if match is None:
                row = _csv_row_by_title(title)
                if row and (row.get("arxiv_id") or "").strip():
                    paper = _ensure_paper_from_csv(session, conference, title)
                    if paper is None:
                        print(f"  missing paper: {title}")
                        missing.append(title)
                        continue
                    link = _ensure_conference_link(session, paper, conference)
                    title_to_link[normalize_title(paper.title)] = (paper, link)
                    print(f"  created/linked arxiv: {paper.arxiv_id} {paper.title}")
                else:
                    paper = _ensure_paper_from_csv(session, conference, title)
                    if paper is None:
                        print(f"  missing paper: {title}")
                        missing.append(title)
                        continue
                    link = _ensure_conference_link(session, paper, conference)
                    print(f"  created/linked: {paper.title}")
            else:
                paper, link = match
                row = _csv_row_by_title(title)
                if (
                    row
                    and (row.get("arxiv_id") or "").strip()
                    and paper.source == "external"
                ):
                    cvf_html = (row.get("cvf_html_url") or "").strip()
                    arxiv_paper, _ = _get_or_create_arxiv_paper(
                        session, row, seed_authors=False
                    )
                    _merge_external_duplicate(session, arxiv_paper, cvf_html)
                    link = _ensure_conference_link(session, arxiv_paper, conference)
                    paper = arxiv_paper
                    print(f"  migrated external -> arxiv: {paper.arxiv_id}")

            link.award = AWARD
            paper.proceeding = FINALIST_PROCEEDING
            finalist_paper_ids.add(paper.id)
            updated += 1
            print(f"  {paper.title} -> {AWARD}")

        stale_links = (
            session.query(PaperConference, Paper)
            .join(Paper, Paper.id == PaperConference.paper_id)
            .filter(
                PaperConference.conference_id == conference.id,
                PaperConference.award == AWARD,
            )
            .all()
        )
        for link, paper in stale_links:
            if link.paper_id in finalist_paper_ids:
                continue
            link.award = None
            if paper.proceeding == FINALIST_PROCEEDING:
                paper.proceeding = PROCEEDING
            print(
                f"  cleared stale finalist: {paper.arxiv_id or paper.id} {paper.title}"
            )

        session.commit()
        print(f"Updated {updated} awards ({len(missing)} missing)")
        if missing:
            sys.exit(1)
    except Exception as exc:
        session.rollback()
        print(f"Failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
