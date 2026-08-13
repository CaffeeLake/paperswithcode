"""Authoritative resolution of internal ``paper:`` citations."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.services.paper_service import PaperNotFoundError, PaperService
from backend.utils.urls import parse_arxiv_url

_PAPER_LINK = re.compile(
    r"\[(?P<label>[^\]\n]{1,500})\]\(paper:(?P<route_id>[^) \t\n]{1,200})\)"
)
_ARXIV_URL = (
    r"https://(?:www\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"\d{4}\.\d{4,5}(?:v\d+)?(?:\.pdf)?(?:[?#][^\s<>)]+)?"
)
_ARXIV_LINK = re.compile(
    rf"(?:"
    rf"\[(?P<label>[^\]\n]{{1,500}})\]\((?P<markdown_url>{_ARXIV_URL})\)"
    rf"|<(?P<autolink_url>{_ARXIV_URL})>"
    rf"|(?P<bare_url>(?<![\[(]){_ARXIV_URL})"
    rf")",
    re.IGNORECASE,
)


def _arxiv_url(match: re.Match[str]) -> str:
    return (
        match.group("markdown_url")
        or match.group("autolink_url")
        or match.group("bare_url")
    )


def _cited_references(text: str) -> list[tuple[int, str]]:
    references = [
        (match.start(), match.group("route_id")) for match in _PAPER_LINK.finditer(text)
    ]
    for match in _ARXIV_LINK.finditer(text):
        parsed = parse_arxiv_url(_arxiv_url(match))
        if parsed is not None:
            references.append((match.start(), parsed[0]))
    return sorted(references)


def cited_route_ids(text: str, maximum: int = 20) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for _position, route_id in _cited_references(text):
        if route_id not in seen:
            seen.add(route_id)
            result.append(route_id)
        if len(result) >= maximum:
            break
    return result


def resolve_citation_targets(
    db: Session, text: str, maximum: int = 20
) -> tuple[list[dict], dict[str, str]]:
    service = PaperService(db)
    resolved: list[dict] = []
    resolved_targets: dict[str, str] = {}
    for route_id in cited_route_ids(text, maximum):
        try:
            paper = service.get_paper_by_id_or_arxiv(route_id)
        except PaperNotFoundError:
            continue
        canonical_route_id = paper.arxiv_id or str(paper.id)
        resolved_targets[route_id] = canonical_route_id
        resolved.append(
            {
                "position": len(resolved),
                "route_id": canonical_route_id,
                "title": paper.title,
                "source_url": paper.source_url or paper.url_abs,
                "thumbnail_url": paper.thumbnail_url,
                "arxiv_id": paper.arxiv_id,
                "authors": paper.authors[:50],
                "published": paper.published.isoformat() if paper.published else None,
                "conference": paper.conference_name or paper.conference,
                "citation_count": paper.citation_count,
            }
        )
    return resolved, resolved_targets


def resolve_citations(db: Session, text: str, maximum: int = 20) -> list[dict]:
    resolved, _resolved_targets = resolve_citation_targets(db, text, maximum)
    return resolved


def normalize_paper_links(text: str, resolved_targets: dict[str, str]) -> str:
    """Canonicalize resolved paper citations, including trusted ArXiv URLs."""

    def replace(match: re.Match[str]) -> str:
        canonical_route_id = resolved_targets.get(match.group("route_id"))
        if canonical_route_id is None:
            return match.group("label")
        return f"[{match.group('label')}](paper:{canonical_route_id})"

    normalized = _PAPER_LINK.sub(replace, text)

    def replace_arxiv(match: re.Match[str]) -> str:
        url = _arxiv_url(match)
        parsed = parse_arxiv_url(url)
        canonical_route_id = (
            resolved_targets.get(parsed[0]) if parsed is not None else None
        )
        if canonical_route_id is None:
            return match.group(0)
        label = match.group("label") or url
        return f"[{label}](paper:{canonical_route_id})"

    return _ARXIV_LINK.sub(replace_arxiv, normalized)
