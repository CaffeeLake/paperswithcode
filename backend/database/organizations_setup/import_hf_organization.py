#!/usr/bin/env python3
"""
Bootstrap an organization from Hugging Face and link its papers.

Given a Hugging Face organization slug (e.g. ``nvidia``), this script:

1. Upserts an ``organizations`` row from the HF org overview API
   (name, logo/avatar, hf_url) and the org papers page (website).
2. Reads the authoritative ``orgPapers`` list embedded in the public
   ``https://huggingface.co/<slug>/papers`` page (all papers HF attributes
   to the org).
3. Links each HF paper to the org via ``paper_organizations`` when a local
   ``papers`` row with the same ArXiv id already exists. Unmatched HF papers
   are reported (they can be imported from ArXiv later).

Usage:
    uv run --env-file backend/keys.env \
        python backend/database/organizations_setup/import_hf_organization.py nvidia
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import sys
from typing import Optional

import requests
from huggingface_hub.utils import build_hf_headers
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Organization, Paper, PaperOrganization

HF_BASE = "https://huggingface.co"
LINK_SOURCE = "hf_org_papers"
REQUEST_TIMEOUT = 30


def fetch_org_overview(slug: str) -> dict:
    """Fetch name, avatar (logo), and counts from the HF org overview API."""
    url = f"{HF_BASE}/api/organizations/{slug}/overview"
    resp = requests.get(url, headers=build_hf_headers(), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _extract_balanced_array(text: str, start_key: str) -> Optional[str]:
    """Return the JSON array literal that follows ``start_key`` in ``text``.

    Scans from the opening ``[`` and balances brackets so the returned slice
    is a self-contained, parseable JSON array.
    """
    key_idx = text.find(start_key)
    if key_idx == -1:
        return None
    open_idx = text.find("[", key_idx)
    if open_idx == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(open_idx, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1]
    return None


def fetch_org_papers_page(slug: str) -> tuple[list[dict], Optional[str]]:
    """Fetch the org papers page and return (org_papers, website_url).

    ``org_papers`` is the authoritative list HF attributes to the org, each
    entry a dict with at least ``arxiv_id`` and ``title``.
    """
    url = f"{HF_BASE}/{slug}/papers"
    resp = requests.get(url, headers=build_hf_headers(), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    text = html_lib.unescape(resp.text)

    website_url: Optional[str] = None
    import re

    match = re.search(r'rel="nofollow"[^>]*>\s*(https?://[^<\s]+)\s*</a>', text)
    if match:
        website_url = match.group(1).strip()

    array_literal = _extract_balanced_array(text, '"orgPapers"')
    papers: list[dict] = []
    if array_literal:
        raw_papers = json.loads(array_literal)
        for entry in raw_papers:
            paper_obj = entry.get("paper") or {}
            arxiv_id = (paper_obj.get("id") or "").strip()
            if not arxiv_id:
                continue
            papers.append(
                {
                    "arxiv_id": arxiv_id,
                    "title": (entry.get("title") or "").strip(),
                }
            )
    return papers, website_url


def upsert_organization(
    db: Session,
    slug: str,
    name: str,
    logo_url: Optional[str],
    website_url: Optional[str],
) -> Organization:
    hf_url = f"{HF_BASE}/{slug}"
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if org is None:
        org = Organization(
            name=name,
            slug=slug,
            hf_url=hf_url,
            logo_url=logo_url,
            website_url=website_url,
        )
        db.add(org)
        db.flush()
    else:
        org.name = name
        org.hf_url = hf_url
        if logo_url:
            org.logo_url = logo_url
        if website_url:
            org.website_url = website_url
    db.commit()
    db.refresh(org)
    return org


def _normalize_title(title: str) -> str:
    return " ".join((title or "").strip().lower().split())


def _find_local_paper(db: Session, arxiv_id: str, title: str) -> Optional[Paper]:
    """Match an HF paper to a local row by ArXiv id, then normalized title."""
    paper = (
        db.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is not None:
        return paper

    normalized = _normalize_title(title)
    if not normalized:
        return None
    return (
        db.query(Paper)
        .filter(func.lower(Paper.title) == normalized, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )


def link_papers(
    db: Session, org: Organization, hf_papers: list[dict]
) -> dict[str, int]:
    stats = {"matched": 0, "linked": 0, "already_linked": 0, "unmatched": 0}
    unmatched_titles: list[str] = []

    for hf_paper in hf_papers:
        arxiv_id = hf_paper["arxiv_id"]
        paper = _find_local_paper(db, arxiv_id, hf_paper["title"])
        if paper is None:
            stats["unmatched"] += 1
            unmatched_titles.append(f"{arxiv_id} - {hf_paper['title']}")
            continue

        stats["matched"] += 1
        existing = (
            db.query(PaperOrganization)
            .filter(
                PaperOrganization.paper_id == paper.id,
                PaperOrganization.organization_id == org.id,
            )
            .first()
        )
        if existing is None:
            db.add(
                PaperOrganization(
                    paper_id=paper.id,
                    organization_id=org.id,
                    source=LINK_SOURCE,
                )
            )
            stats["linked"] += 1
        else:
            stats["already_linked"] += 1

    db.commit()

    if unmatched_titles:
        print(f"\nUnmatched HF papers (no local row): {len(unmatched_titles)}")
        for line in unmatched_titles[:30]:
            print(f"   - {line}")
        if len(unmatched_titles) > 30:
            print(f"   ... and {len(unmatched_titles) - 30} more")

    return stats


def main(slug: str) -> None:
    slug = slug.strip().lower()
    print("=" * 80)
    print(f"Bootstrapping organization from Hugging Face: {slug}")
    print("=" * 80)

    overview = fetch_org_overview(slug)
    name = (overview.get("fullname") or overview.get("name") or slug).strip()
    logo_url = overview.get("avatarUrl")
    print(
        f"name={name!r} logo={'yes' if logo_url else 'no'} "
        f"numPapers={overview.get('numPapers')}"
    )

    hf_papers, website_url = fetch_org_papers_page(slug)
    print(f"Fetched {len(hf_papers)} papers from {HF_BASE}/{slug}/papers")
    if website_url:
        print(f"website={website_url}")

    session = db_manager.session_local()
    try:
        org = upsert_organization(session, slug, name, logo_url, website_url)
        print(f"Organization id={org.id} slug={org.slug}")

        stats = link_papers(session, org, hf_papers)
        print("\n" + "=" * 80)
        print(
            "Done: "
            f"matched={stats['matched']} linked={stats['linked']} "
            f"already_linked={stats['already_linked']} "
            f"unmatched={stats['unmatched']}"
        )
        print("=" * 80)
    except Exception as exc:
        session.rollback()
        print(f"Bootstrap failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bootstrap an organization from Hugging Face"
    )
    parser.add_argument(
        "slug",
        nargs="?",
        default="nvidia",
        help="Hugging Face organization slug (default: nvidia)",
    )
    args = parser.parse_args()
    main(args.slug)
