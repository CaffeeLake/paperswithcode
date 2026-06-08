#!/usr/bin/env python3
"""
Scrape CVPR 2026 papers from the CVF Open Access repository and export to CSV.

Primary source: https://openaccess.thecvf.com/CVPR2026?day=all
Optional cross-link: https://cvpr.thecvf.com/virtual/2026/papers.html
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.utils.paper_utils import GITHUB_URL_PATTERN
from backend.utils.url_fetch import fetch_html
from backend.utils.urls import extract_arxiv_id_from_text, validate_arxiv_id

logger = logging.getLogger(__name__)

OPENACCESS_LISTING_URL = "https://openaccess.thecvf.com/CVPR2026?day=all"
OPENACCESS_BASE = "https://openaccess.thecvf.com"
VIRTUAL_PAPERS_URL = "https://cvpr.thecvf.com/virtual/2026/papers.html"
VIRTUAL_ORAL_URL = "https://cvpr.thecvf.com/virtual/2026/events/Oral"
VIRTUAL_HIGHLIGHTS_URL = "https://cvpr.thecvf.com/virtual/2026/events/Highlights2026"
VIRTUAL_BASE = "https://cvpr.thecvf.com"
POSTER_ID_PATTERN = re.compile(r"/virtual/2026/poster/(\d+)")
ORAL_ID_PATTERN = re.compile(r"/virtual/2026/oral/(\d+)")
LISTING_MAX_BYTES = 20_000_000

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "cvpr2026_papers.csv"
DEFAULT_CHECKPOINT = REPO_ROOT / "data" / "cvpr2026_scrape_checkpoint.jsonl"

PROJECT_PAGE_URL_PATTERN = re.compile(
    r"\bhttps?://(?!(?:github\.com|arxiv\.org|openaccess\.thecvf\.com|cvpr\.thecvf\.com|www\.thecvf\.com))[^\s<>\"']+",
    re.IGNORECASE,
)

CSV_COLUMNS = [
    "arxiv_id",
    "title",
    "abstract",
    "authors",
    "github_url",
    "project_page_url",
    "cvf_html_url",
    "virtual_poster_url",
    "pdf_url",
    "presentation_type",
]


@dataclass
class PaperRow:
    title: str
    authors: str = ""
    arxiv_id: str = ""
    abstract: str = ""
    github_url: str = ""
    project_page_url: str = ""
    cvf_html_url: str = ""
    virtual_poster_url: str = ""
    pdf_url: str = ""
    presentation_type: str = ""


def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title)
    for ch in "\u2018\u2019\u201a\u2032\u0060\u00b4":
        title = title.replace(ch, "'")
    for ch in "\u2013\u2014\u2212":
        title = title.replace(ch, "-")
    return " ".join(title.casefold().split())


def extract_poster_id(url: str) -> str:
    match = POSTER_ID_PATTERN.search(url or "")
    return match.group(1) if match else ""


def parse_event_page_titles(html: str) -> set[str]:
    """Extract normalized paper titles from a CVPR virtual events listing page."""
    soup = BeautifulSoup(html, "html.parser")
    titles: set[str] = set()
    for card in soup.select(".event-card"):
        title_el = card.select_one(".event-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if title:
            titles.add(normalize_title(title))
    return titles


def parse_highlight_poster_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    poster_ids: set[str] = set()
    for card in soup.select(".event-card"):
        for link in card.select("a[href]"):
            poster_id = extract_poster_id(link["href"])
            if poster_id:
                poster_ids.add(poster_id)
    return poster_ids


def parse_oral_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    oral_ids: set[str] = set()
    for card in soup.select(".event-card"):
        for link in card.select("a[href]"):
            match = ORAL_ID_PATTERN.search(link["href"])
            if match:
                oral_ids.add(match.group(1))
    return oral_ids


async def fetch_oral_poster_ids(
    oral_ids: set[str], concurrency: int = 20
) -> dict[str, str]:
    """Map oral page IDs to their linked poster page IDs."""
    if not oral_ids:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    oral_to_poster: dict[str, str] = {}

    async def fetch_one(oral_id: str) -> None:
        async with semaphore:
            html = await fetch_large_html(
                f"{VIRTUAL_BASE}/virtual/2026/oral/{oral_id}",
                timeout_seconds=20.0,
            )
        if not html:
            return
        match = POSTER_ID_PATTERN.search(html)
        if match:
            oral_to_poster[oral_id] = match.group(1)

    await asyncio.gather(*(fetch_one(oral_id) for oral_id in sorted(oral_ids)))
    return oral_to_poster


async def fetch_large_html(url: str, timeout_seconds: float = 60.0) -> Optional[str]:
    """Fetch a full HTML page without byte-cap truncation."""
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; paperswithcode.co CVPR2026 scraper)"
    }
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            raw = await response.read()
            if len(raw) > LISTING_MAX_BYTES:
                raise RuntimeError(
                    f"Page exceeded {LISTING_MAX_BYTES} bytes: {url} ({len(raw)} bytes)"
                )
            encoding = response.charset or "utf-8"
            return raw.decode(encoding, errors="replace")


def parse_listing_html(html: str) -> list[PaperRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[PaperRow] = []

    for dt in soup.find_all("dt", class_="ptitle"):
        link = dt.find("a", href=True)
        if not link:
            continue

        title = link.get_text(strip=True)
        cvf_html_url = urljoin(OPENACCESS_BASE, link["href"])

        authors: list[str] = []
        arxiv_id = ""
        pdf_url = ""

        sibling = dt.find_next_sibling()
        while sibling and sibling.name != "dt":
            if sibling.name == "dd":
                for form in sibling.find_all("form", class_="authsearch"):
                    author_input = form.find("input", attrs={"name": "query_author"})
                    if author_input and author_input.get("value"):
                        authors.append(author_input["value"].strip())

                for a in sibling.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True).lower()
                    if text == "arxiv" or "arxiv.org" in href:
                        parsed = extract_arxiv_id_from_text(href)
                        if parsed and validate_arxiv_id(parsed):
                            arxiv_id = parsed
                    elif text == "pdf" and not pdf_url:
                        pdf_url = urljoin(OPENACCESS_BASE, href)

            sibling = sibling.find_next_sibling()

        rows.append(
            PaperRow(
                title=title,
                authors="; ".join(authors),
                arxiv_id=arxiv_id,
                cvf_html_url=cvf_html_url,
                pdf_url=pdf_url,
            )
        )

    return rows


def parse_abstract_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    abstract_div = soup.find("div", id="abstract")
    if not abstract_div:
        return ""
    return abstract_div.get_text(" ", strip=True)


def parse_virtual_poster_map(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title_to_url: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/virtual/2026/poster/" not in href:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        poster_url = urljoin(VIRTUAL_BASE, href)
        title_to_url[normalize_title(title)] = poster_url

    return title_to_url


def load_checkpoint(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    abstracts: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            cvf_html_url = record.get("cvf_html_url", "")
            if cvf_html_url:
                abstracts[cvf_html_url] = record.get("abstract", "")
    return abstracts


def append_checkpoint(path: Path, cvf_html_url: str, abstract: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"cvf_html_url": cvf_html_url, "abstract": abstract}))
        f.write("\n")


async def fetch_abstracts(
    rows: list[PaperRow],
    checkpoint_path: Path,
    concurrency: int,
) -> None:
    checkpoint = load_checkpoint(checkpoint_path)
    pending = [row for row in rows if row.cvf_html_url not in checkpoint]

    for row in rows:
        if row.cvf_html_url in checkpoint:
            row.abstract = checkpoint[row.cvf_html_url]

    if not pending:
        logger.info("All abstracts loaded from checkpoint")
        return

    logger.info("Fetching %d abstracts (%d cached)", len(pending), len(checkpoint))
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(row: PaperRow) -> None:
        async with semaphore:
            html = await fetch_html(row.cvf_html_url, timeout_seconds=20.0)
            abstract = parse_abstract_html(html) if html else ""
            row.abstract = abstract
            append_checkpoint(checkpoint_path, row.cvf_html_url, abstract)

    await asyncio.gather(*(fetch_one(row) for row in pending))


def extract_github_from_abstract(abstract: str) -> str:
    match = re.search(GITHUB_URL_PATTERN, abstract or "")
    return match.group(0).rstrip(".,;)") if match else ""


def extract_project_page_from_abstract(abstract: str) -> str:
    for match in PROJECT_PAGE_URL_PATTERN.finditer(abstract or ""):
        url = match.group(0).rstrip(".,;)")
        if url:
            return url
    return ""


async def fetch_hf_urls(arxiv_id: str, session) -> tuple[str, str]:
    import aiohttp
    from huggingface_hub.utils import build_hf_headers

    headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
    url = f"https://huggingface.co/api/papers/{arxiv_id}"
    for attempt in range(4):
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 429:
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status == 404:
                    return "", ""
                response.raise_for_status()
                data = await response.json()
                return data.get("githubRepo", "") or "", data.get(
                    "projectPage", ""
                ) or ""
        except aiohttp.ClientError:
            if attempt == 3:
                return "", ""
            await asyncio.sleep(2**attempt)
    return "", ""


async def enrich_urls(rows: list[PaperRow], hf_concurrency: int) -> None:
    import aiohttp

    semaphore = asyncio.Semaphore(hf_concurrency)

    async with aiohttp.ClientSession() as session:

        async def enrich_one(row: PaperRow) -> None:
            if row.arxiv_id:
                async with semaphore:
                    github_url, project_page_url = await fetch_hf_urls(
                        row.arxiv_id, session
                    )
                    await asyncio.sleep(0.15)
                row.github_url = github_url
                row.project_page_url = project_page_url

            if not row.github_url:
                row.github_url = extract_github_from_abstract(row.abstract)
            if not row.project_page_url:
                row.project_page_url = extract_project_page_from_abstract(row.abstract)

        await asyncio.gather(*(enrich_one(row) for row in rows))


def attach_virtual_poster_urls(
    rows: list[PaperRow], title_to_poster: dict[str, str]
) -> int:
    matched = 0
    for row in rows:
        poster_url = title_to_poster.get(normalize_title(row.title), "")
        row.virtual_poster_url = poster_url
        if poster_url:
            matched += 1
    return matched


def attach_presentation_types(
    rows: list[PaperRow],
    oral_titles: set[str],
    highlight_titles: set[str],
    oral_poster_ids: set[str],
    highlight_poster_ids: set[str],
) -> tuple[int, int]:
    oral_matched = 0
    highlight_matched = 0
    for row in rows:
        poster_id = extract_poster_id(row.virtual_poster_url)
        key = normalize_title(row.title)
        if poster_id in oral_poster_ids or key in oral_titles:
            row.presentation_type = "oral"
            oral_matched += 1
        elif poster_id in highlight_poster_ids or key in highlight_titles:
            row.presentation_type = "highlight"
            highlight_matched += 1
        else:
            row.presentation_type = ""
    return oral_matched, highlight_matched


def read_csv_rows(path: Path) -> list[PaperRow]:
    rows: list[PaperRow] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for record in reader:
            rows.append(
                PaperRow(
                    title=record.get("title", ""),
                    authors=record.get("authors", ""),
                    arxiv_id=record.get("arxiv_id", ""),
                    abstract=record.get("abstract", ""),
                    github_url=record.get("github_url", ""),
                    project_page_url=record.get("project_page_url", ""),
                    cvf_html_url=record.get("cvf_html_url", ""),
                    virtual_poster_url=record.get("virtual_poster_url", ""),
                    pdf_url=record.get("pdf_url", ""),
                    presentation_type=record.get("presentation_type", ""),
                )
            )
    return rows


async def fetch_presentation_type_data() -> tuple[
    set[str], set[str], set[str], set[str]
]:
    oral_html = await fetch_large_html(VIRTUAL_ORAL_URL)
    highlight_html = await fetch_large_html(VIRTUAL_HIGHLIGHTS_URL)

    oral_titles = parse_event_page_titles(oral_html) if oral_html else set()
    highlight_titles = (
        parse_event_page_titles(highlight_html) if highlight_html else set()
    )
    highlight_poster_ids = (
        parse_highlight_poster_ids(highlight_html) if highlight_html else set()
    )

    oral_ids = parse_oral_ids(oral_html) if oral_html else set()
    oral_to_poster = await fetch_oral_poster_ids(oral_ids)
    oral_poster_ids = set(oral_to_poster.values())

    return oral_titles, highlight_titles, oral_poster_ids, highlight_poster_ids


def write_csv(rows: list[PaperRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows, key=lambda r: (r.arxiv_id or "zzz", r.title.casefold()))

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow({col: getattr(row, col, "") or "" for col in CSV_COLUMNS})


def print_summary(
    rows: list[PaperRow],
    virtual_matched: int,
    oral_matched: int = 0,
    highlight_matched: int = 0,
) -> None:
    total = len(rows)
    with_arxiv = sum(1 for r in rows if r.arxiv_id)
    with_abstract = sum(1 for r in rows if r.abstract)
    with_github = sum(1 for r in rows if r.github_url)
    with_project = sum(1 for r in rows if r.project_page_url)

    logger.info("=" * 60)
    logger.info("CVPR 2026 scrape summary")
    logger.info("Total papers: %d", total)
    logger.info("With arxiv_id: %d (%.1f%%)", with_arxiv, 100 * with_arxiv / total)
    logger.info(
        "With abstract: %d (%.1f%%)", with_abstract, 100 * with_abstract / total
    )
    logger.info("With github_url: %d (%.1f%%)", with_github, 100 * with_github / total)
    logger.info(
        "With project_page_url: %d (%.1f%%)",
        with_project,
        100 * with_project / total,
    )
    logger.info(
        "Virtual poster matched: %d / %d (%.1f%%)",
        virtual_matched,
        total,
        100 * virtual_matched / total,
    )
    logger.info("Oral papers: %d", oral_matched)
    logger.info("Highlight papers: %d", highlight_matched)
    logger.info("=" * 60)


async def run(args: argparse.Namespace) -> None:
    if args.presentation_types_only:
        if not args.output.exists():
            raise RuntimeError(f"CSV not found: {args.output}")
        rows = read_csv_rows(args.output)
        logger.info("Loaded %d rows from %s", len(rows), args.output)
    else:
        logger.info("Fetching listing page: %s", OPENACCESS_LISTING_URL)
        listing_html = await fetch_large_html(OPENACCESS_LISTING_URL)
        if not listing_html:
            raise RuntimeError(
                f"Failed to fetch listing page: {OPENACCESS_LISTING_URL}"
            )

        rows = parse_listing_html(listing_html)
        logger.info("Parsed %d papers from listing", len(rows))

        await fetch_abstracts(rows, args.checkpoint, args.concurrency)

    virtual_matched = sum(1 for r in rows if r.virtual_poster_url)
    if not args.presentation_types_only:
        logger.info("Fetching virtual poster page: %s", VIRTUAL_PAPERS_URL)
        virtual_html = await fetch_large_html(VIRTUAL_PAPERS_URL)
        virtual_matched = 0
        if virtual_html:
            title_to_poster = parse_virtual_poster_map(virtual_html)
            logger.info("Parsed %d virtual poster titles", len(title_to_poster))
            virtual_matched = attach_virtual_poster_urls(rows, title_to_poster)
        else:
            logger.warning("Could not fetch virtual poster page; skipping cross-link")

        if not args.skip_enrichment:
            logger.info("Enriching GitHub/project URLs via HF API + abstract regex")
            await enrich_urls(rows, args.hf_concurrency)

    logger.info("Fetching oral page: %s", VIRTUAL_ORAL_URL)
    logger.info("Fetching highlights page: %s", VIRTUAL_HIGHLIGHTS_URL)
    (
        oral_titles,
        highlight_titles,
        oral_poster_ids,
        highlight_poster_ids,
    ) = await fetch_presentation_type_data()
    logger.info(
        "Parsed %d oral titles, %d highlight titles, %d oral poster IDs, %d highlight poster IDs",
        len(oral_titles),
        len(highlight_titles),
        len(oral_poster_ids),
        len(highlight_poster_ids),
    )
    oral_matched, highlight_matched = attach_presentation_types(
        rows,
        oral_titles,
        highlight_titles,
        oral_poster_ids,
        highlight_poster_ids,
    )

    write_csv(rows, args.output)
    logger.info("Wrote CSV: %s", args.output)
    print_summary(rows, virtual_matched, oral_matched, highlight_matched)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape CVPR 2026 papers to CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="JSONL checkpoint for abstract fetches",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Concurrent abstract page fetches",
    )
    parser.add_argument(
        "--hf-concurrency",
        type=int,
        default=3,
        help="Concurrent Hugging Face API requests",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip HF/regex URL enrichment",
    )
    parser.add_argument(
        "--presentation-types-only",
        action="store_true",
        help="Only fetch oral/highlight labels and update an existing CSV",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
