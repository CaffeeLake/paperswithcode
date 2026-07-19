"""Resolve Papers with Code paper references consistently across CLI commands."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import Paper


def normalize_paper_reference(value: str) -> str:
    """Accept a PwC paper URL, arXiv ID, or numeric external-paper ID."""
    reference = value.strip()
    if "://" in reference:
        parsed = urlparse(reference)
        if parsed.netloc.lower() not in {"paperswithcode.co", "www.paperswithcode.co"}:
            raise ValueError("Paper URL must be on paperswithcode.co")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2 or parts[0] != "paper":
            raise ValueError("Expected a Papers with Code /paper/<id> URL")
        reference = parts[1]
    if not reference or "/" in reference:
        raise ValueError("Invalid paper reference")
    return re.sub(r"v\d+$", "", reference)


def resolve_paper(db: Session, value: str) -> tuple[Paper, str]:
    """Return the database paper and its canonical public route identifier."""
    reference = normalize_paper_reference(value)
    if reference.isdigit():
        statement = select(Paper).where(Paper.id == int(reference))
    else:
        statement = select(Paper).where(
            Paper.arxiv_id == reference,
            Paper.is_latest_version,
        )
    paper = db.execute(statement).scalar_one_or_none()
    if not paper:
        raise ValueError(f"Paper not found: {reference}")
    return paper, paper.arxiv_id or str(paper.id)
