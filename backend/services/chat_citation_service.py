"""Authoritative resolution of internal ``paper:`` citations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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
_S2_COMMAND = re.compile(r"(?:^|\s)s2\s+(?:search|refs|citations)\b")
_ARXIV_ID = re.compile(r"^(?P<id>\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\([^\)\n]*\)")
_REFERENCE_LINK = re.compile(r"!?\[[^\]\n]+\]\[[^\]\n]*\]")
_INLINE_CODE = re.compile(r"(?P<fence>`+).*?(?P=fence)", re.DOTALL)
_REFERENCE_DEFINITION = re.compile(
    r"^ {0,3}\[(?P<label>[^\]\n]+)\]:\s*\S+", re.MULTILINE
)
_HTTPS_URL = re.compile(r"https://[^\s<>]+")


@dataclass(frozen=True)
class PaperCitationCandidate:
    title: str
    arxiv_id: str | None
    semantic_scholar_id: str | None
    semantic_scholar_url: str | None
    route_id: str | None = None
    authors: tuple[str, ...] = ()
    published: str | None = None
    citation_count: int | None = None
    excerpt: str | None = None


def _normalized_arxiv_id(value: object) -> str | None:
    match = _ARXIV_ID.fullmatch(str(value or "").strip())
    return match.group("id") if match else None


def _candidate_from_s2_item(item: dict[str, Any]) -> PaperCitationCandidate | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    external_ids = item.get("externalIds")
    arxiv = (
        external_ids.get("ArXiv")
        if isinstance(external_ids, dict)
        else item.get("arxiv")
    )
    authors = tuple(
        str(author.get("name") or "").strip()
        for author in item.get("authors") or []
        if isinstance(author, dict) and str(author.get("name") or "").strip()
    )
    year = item.get("year")
    count = item.get("citationCount")
    paper_id = str(item.get("paperId") or "").strip() or None
    url = str(item.get("url") or "").strip() or None
    if url is None and paper_id:
        url = f"https://www.semanticscholar.org/paper/{paper_id}"
    return PaperCitationCandidate(
        title=title,
        arxiv_id=_normalized_arxiv_id(arxiv),
        semantic_scholar_id=paper_id,
        semantic_scholar_url=url,
        authors=authors,
        published=str(year) if year is not None else None,
        citation_count=int(count) if isinstance(count, (int, float)) else None,
        excerpt=str(item.get("abstract") or "").strip()[:4000] or None,
    )


def extract_s2_candidates(
    command: str, content: list[dict[str, Any]]
) -> list[PaperCitationCandidate]:
    """Extract bounded paper metadata only from a successful ``s2`` command."""
    if not _S2_COMMAND.search(command):
        return []
    text = "".join(
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )
    candidates: list[PaperCitationCandidate] = []
    lines = text.splitlines()
    try:
        header = lines.index("paperId\tyear\tcites\tarxiv\ttitle")
    except ValueError:
        header = -1
    if header >= 0:
        for line in lines[header + 1 :]:
            values = line.split("\t", 4)
            if len(values) != 5:
                continue
            paper_id, year, cites, arxiv, title = values
            candidate = _candidate_from_s2_item(
                {
                    "paperId": paper_id,
                    "year": int(year) if year.isdigit() else None,
                    "citationCount": int(cites) if cites.isdigit() else None,
                    "arxiv": arxiv,
                    "title": title.replace("\\t", "\t").replace("\\n", "\n"),
                }
            )
            if candidate is not None:
                candidates.append(candidate)
            if len(candidates) >= 100:
                return candidates
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        candidate = _candidate_from_s2_item(payload)
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= 100:
            break
    return candidates


def candidates_from_citation_history(
    citations: list[dict[str, Any]],
) -> list[PaperCitationCandidate]:
    candidates: list[PaperCitationCandidate] = []
    for citation in citations:
        if (
            citation.get("kind") == "external_source"
            and citation.get("source_type") != "paper"
        ):
            continue
        title = str(citation.get("title") or "").strip()
        if not title:
            continue
        authors = tuple(
            str(author).strip()
            for author in citation.get("authors") or []
            if str(author).strip()
        )
        candidates.append(
            PaperCitationCandidate(
                title=title,
                arxiv_id=_normalized_arxiv_id(citation.get("arxiv_id")),
                semantic_scholar_id=(
                    str(citation.get("semantic_scholar_id") or "").strip() or None
                ),
                semantic_scholar_url=(
                    str(citation.get("source_url") or "").strip() or None
                ),
                route_id=str(citation.get("route_id") or "").strip() or None,
                authors=authors,
                published=citation.get("published"),
                citation_count=citation.get("citation_count"),
                excerpt=citation.get("excerpt"),
            )
        )
    return candidates


def _code_protected_ranges(text: str) -> list[tuple[int, int]]:
    protected: list[tuple[int, int]] = []
    fence: str | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence is not None:
            protected.append((offset, offset + len(line)))
            if marker and marker.group(1).startswith(fence[0]):
                fence = None
        elif marker:
            fence = marker.group(1)
            protected.append((offset, offset + len(line)))
        offset += len(line)
    protected.extend(
        (match.start(), match.end()) for match in _INLINE_CODE.finditer(text)
    )
    return protected


def _markdown_protected_ranges(text: str) -> list[tuple[int, int]]:
    protected = _code_protected_ranges(text)
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        stripped = line.lstrip()
        if re.match(r"#{1,6}(?:\s|$)", stripped):
            protected.append((offset, offset + len(line)))
        offset += len(line)
    for index in range(len(lines) - 1):
        if re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1].rstrip("\n\r")):
            protected.append(
                (offsets[index], offsets[index + 1] + len(lines[index + 1]))
            )
    for pattern in (_MARKDOWN_LINK, _REFERENCE_LINK, _HTTPS_URL):
        protected.extend(
            (match.start(), match.end()) for match in pattern.finditer(text)
        )
    shortcut_labels = {
        " ".join(match.group("label").split()).casefold()
        for match in _REFERENCE_DEFINITION.finditer(text)
    }
    if shortcut_labels:
        for match in re.finditer(r"!?\[(?P<label>[^\]\n]+)\]", text):
            normalized_label = " ".join(match.group("label").split()).casefold()
            if normalized_label in shortcut_labels:
                protected.append((match.start(), match.end()))
    return protected


def _first_unprotected_match(text: str, title: str) -> re.Match[str] | None:
    protected = _markdown_protected_ranges(text)
    pattern = rf"(?<!\w){re.escape(title)}(?!\w)"
    for match in re.finditer(pattern, text, re.IGNORECASE):
        if not any(
            match.start() < end and match.end() > start for start, end in protected
        ):
            return match
    return None


def _candidate_identity(candidate: PaperCitationCandidate) -> tuple[str, str] | None:
    if candidate.arxiv_id:
        return "arxiv", candidate.arxiv_id
    if candidate.route_id:
        return "route", candidate.route_id
    if candidate.semantic_scholar_id:
        return "semantic_scholar", candidate.semantic_scholar_id
    return None


def normalize_s2_catalog_links(
    text: str, candidates: list[PaperCitationCandidate], db: Session
) -> str:
    """Upgrade authored S2 links when their exact arXiv ID exists in PwC."""
    normalized = text
    service = PaperService(db)
    for candidate in candidates:
        if not candidate.arxiv_id or not candidate.semantic_scholar_url:
            continue
        target = re.compile(rf"\]\({re.escape(candidate.semantic_scholar_url)}\)")
        if target.search(normalized) is None:
            continue
        try:
            paper = service.get_paper_by_id_or_arxiv(candidate.arxiv_id)
        except PaperNotFoundError:
            continue
        route_id = paper.arxiv_id or str(paper.id)
        protected = _code_protected_ranges(normalized)
        normalized = target.sub(
            lambda match: (
                match.group(0)
                if any(
                    match.start() < end and match.end() > start
                    for start, end in protected
                )
                else f"](paper:{route_id})"
            ),
            normalized,
        )
    return normalized


def repair_exact_paper_titles(
    text: str, candidates: list[PaperCitationCandidate], db: Session
) -> tuple[str, dict[str, PaperCitationCandidate]]:
    """Link the first unique exact paper title grounded in trusted tool output."""
    by_title: dict[str, list[PaperCitationCandidate]] = {}
    for candidate in candidates:
        by_title.setdefault(candidate.title.casefold(), []).append(candidate)
    repaired = text
    used: dict[str, PaperCitationCandidate] = {}
    service = PaperService(db)
    for title_key, matches in by_title.items():
        identities = {_candidate_identity(item) for item in matches}
        if len(identities) != 1:
            continue
        candidate = matches[0]
        found = _first_unprotected_match(repaired, candidate.title)
        if found is None:
            continue
        route_id: str | None = None
        if candidate.route_id or candidate.arxiv_id:
            try:
                paper = service.get_paper_by_id_or_arxiv(
                    candidate.route_id or candidate.arxiv_id or ""
                )
                route_id = paper.arxiv_id or str(paper.id)
            except PaperNotFoundError:
                pass
        destination = (
            f"paper:{route_id}"
            if route_id
            else (
                f"https://arxiv.org/abs/{candidate.arxiv_id}"
                if candidate.arxiv_id
                else candidate.semantic_scholar_url
            )
        )
        if not destination:
            continue
        label = found.group(0)
        repaired = (
            repaired[: found.start()]
            + f"[{label}]({destination})"
            + repaired[found.end() :]
        )
        used[title_key] = candidate
    return repaired, used


def citation_format_counts(
    text: str,
    candidates: list[PaperCitationCandidate],
    repaired_title_keys: set[str],
) -> dict[str, int | float]:
    by_title: dict[str, list[PaperCitationCandidate]] = {}
    for candidate in candidates:
        by_title.setdefault(candidate.title.casefold(), []).append(candidate)
    linked_labels = {
        match.group("label").casefold()
        for match in re.finditer(
            r"\[(?P<label>[^\]\n]+)\]\((?:paper:|https://)[^)\n]+\)", text
        )
    }
    mentioned: set[str] = set()
    authored: set[str] = set()
    for title_key, matches in by_title.items():
        identities = {_candidate_identity(item) for item in matches}
        if len(identities) != 1:
            continue
        if title_key in linked_labels:
            mentioned.add(title_key)
            authored.add(title_key)
        elif _first_unprotected_match(text, matches[0].title) is not None:
            mentioned.add(title_key)
    total = len(mentioned)
    repaired = len(mentioned & repaired_title_keys)
    correctly_authored = len(authored)
    unresolved = max(0, total - correctly_authored - repaired)
    return {
        "paper_references": total,
        "authored_correctly": correctly_authored,
        "repaired": repaired,
        "unresolved": unresolved,
        "compliance_rate": round(correctly_authored / total, 4) if total else 1.0,
    }


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
