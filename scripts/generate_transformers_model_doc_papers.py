"""Generate a CSV mapping every Transformers `model_doc` page to its paper.

Source: https://github.com/huggingface/transformers/tree/main/docs/source/en/model_doc

For every `.md` file in that directory we extract any arXiv identifier from
either an `https://huggingface.co/papers/<id>` link or a direct
`https://arxiv.org/abs/<id>` / `https://arxiv.org/pdf/<id>` link. When a doc
links to multiple arXiv papers we emit one row per unique id. Docs without any
arXiv link are marked with `arxiv_id=external`.

Output: data/transformers_model_doc_papers.csv
"""

from __future__ import annotations

import csv
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

REPO_OWNER = "huggingface"
REPO_NAME = "transformers"
DOC_DIR = "docs/source/en/model_doc"
BRANCH = "main"

CONTENTS_API = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DOC_DIR}"
    f"?ref={BRANCH}"
)
RAW_BASE = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/{DOC_DIR}"
)
HTML_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/blob/{BRANCH}/{DOC_DIR}"

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "transformers_model_doc_papers.csv"
)

# arXiv id formats:
#   new style: 2302.13971, 2302.13971v2, 1810.04805
#   old style: cs/0612001, hep-th/9901001
ARXIV_NEW_RE = r"\d{4}\.\d{4,5}"
ARXIV_OLD_RE = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}"
ARXIV_ID_RE = rf"(?:{ARXIV_NEW_RE}|{ARXIV_OLD_RE})"

HF_PAPERS_LINK_RE = re.compile(
    rf"\[([^\]]+)\]\(https?://huggingface\.co/papers/({ARXIV_ID_RE})(?:v\d+)?\)"
)
ARXIV_ABS_LINK_RE = re.compile(
    rf"\[([^\]]+)\]\(https?://arxiv\.org/(?:abs|pdf)/({ARXIV_ID_RE})(?:v\d+)?(?:\.pdf)?\)"
)
HF_PAPERS_BARE_RE = re.compile(
    rf"https?://huggingface\.co/papers/({ARXIV_ID_RE})(?:v\d+)?"
)
ARXIV_BARE_RE = re.compile(
    rf"https?://arxiv\.org/(?:abs|pdf)/({ARXIV_ID_RE})(?:v\d+)?(?:\.pdf)?"
)


def _http_get(url: str, *, accept: str | None = None) -> httpx.Response:
    headers: dict[str, str] = {
        "User-Agent": "paperswithcode-transformers-csv/1.0",
    }
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("PWC_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response


def list_model_doc_files() -> list[str]:
    """Return the list of `.md` filenames in the model_doc directory."""
    response = _http_get(CONTENTS_API, accept="application/vnd.github+json")
    entries = response.json()
    files = [
        entry["name"]
        for entry in entries
        if entry.get("type") == "file" and entry["name"].endswith(".md")
    ]
    files.sort()
    return files


def fetch_doc(filename: str) -> str:
    response = _http_get(f"{RAW_BASE}/{filename}")
    return response.text


def extract_paper_links(markdown: str) -> list[tuple[str, str, str]]:
    """Return a list of `(arxiv_id, paper_url, link_text)` tuples.

    Order is preserved from the first occurrence in the document, deduplicated
    on the normalized arXiv id.
    """
    seen: dict[str, tuple[str, str, str]] = {}

    for match in HF_PAPERS_LINK_RE.finditer(markdown):
        link_text, arxiv_id = match.group(1).strip(), match.group(2)
        url = f"https://huggingface.co/papers/{arxiv_id}"
        seen.setdefault(arxiv_id, (arxiv_id, url, link_text))

    for match in ARXIV_ABS_LINK_RE.finditer(markdown):
        link_text, arxiv_id = match.group(1).strip(), match.group(2)
        url = f"https://arxiv.org/abs/{arxiv_id}"
        seen.setdefault(arxiv_id, (arxiv_id, url, link_text))

    for match in HF_PAPERS_BARE_RE.finditer(markdown):
        arxiv_id = match.group(1)
        url = f"https://huggingface.co/papers/{arxiv_id}"
        seen.setdefault(arxiv_id, (arxiv_id, url, ""))

    for match in ARXIV_BARE_RE.finditer(markdown):
        arxiv_id = match.group(1)
        url = f"https://arxiv.org/abs/{arxiv_id}"
        seen.setdefault(arxiv_id, (arxiv_id, url, ""))

    return list(seen.values())


def build_rows(filename: str, markdown: str) -> list[dict[str, str]]:
    stem = filename[:-3] if filename.endswith(".md") else filename
    source_url = f"{HTML_BASE}/{filename}"
    papers = extract_paper_links(markdown)

    if not papers:
        return [
            {
                "model_doc": stem,
                "model_doc_file": filename,
                "paper_title": "",
                "arxiv_id": "external",
                "paper_url": "",
                "source_url": source_url,
            }
        ]

    rows: list[dict[str, str]] = []
    for arxiv_id, paper_url, link_text in papers:
        rows.append(
            {
                "model_doc": stem,
                "model_doc_file": filename,
                "paper_title": link_text,
                "arxiv_id": arxiv_id,
                "paper_url": paper_url,
                "source_url": source_url,
            }
        )
    return rows


def main() -> int:
    print(f"Listing model_doc files from {CONTENTS_API} ...", flush=True)
    filenames = list_model_doc_files()
    print(f"Found {len(filenames)} markdown files.", flush=True)

    rows: list[dict[str, str]] = []
    fetched = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        future_to_name = {pool.submit(fetch_doc, name): name for name in filenames}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            markdown = future.result()
            rows.extend(build_rows(name, markdown))
            fetched += 1
            if fetched % 50 == 0 or fetched == len(filenames):
                print(f"  fetched {fetched}/{len(filenames)}", flush=True)

    rows.sort(key=lambda r: (r["model_doc"], r["arxiv_id"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model_doc",
        "model_doc_file",
        "paper_title",
        "arxiv_id",
        "paper_url",
        "source_url",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total_rows = len(rows)
    unique_docs = len({r["model_doc"] for r in rows})
    external_rows = sum(1 for r in rows if r["arxiv_id"] == "external")
    unique_arxiv = len({r["arxiv_id"] for r in rows if r["arxiv_id"] != "external"})

    print()
    print(
        f"Wrote {OUTPUT_PATH.relative_to(Path.cwd()) if OUTPUT_PATH.is_relative_to(Path.cwd()) else OUTPUT_PATH}"
    )
    print(f"  rows:           {total_rows}")
    print(f"  unique docs:    {unique_docs}")
    print(f"  unique arxiv:   {unique_arxiv}")
    print(f"  external rows:  {external_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
