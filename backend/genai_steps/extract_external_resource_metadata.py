"""
LLM-driven metadata extraction for external resources (vendor blog posts,
technical reports, model release pages, etc.).

Given the URL and rendered text of a page, this returns a structured object
containing the title, abstract/summary, authors, publication date, and any
GitHub repositories or Hugging Face artifact URLs the page mentions.

The extracted metadata is used by `ExternalResourceService.add_from_url` to
populate a `papers` row with `source='external'`.

Usage:
```bash
uv run --env-file backend/keys.env -m \\
    backend.genai_steps.extract_external_resource_metadata \\
    --url https://www.zyphra.com/zaya1-vl-8b-technical-report
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.generators.openrouter_generator import OpenRouterGenerator
from backend.models.generators import Generator, Message
from backend.utils.url_fetch import (
    extract_github_urls,
    extract_hf_repo_urls,
    fetch_html_and_text,
)


logger = logging.getLogger(__name__)


class ExternalResourceMetadata(BaseModel):
    """
    Structured page metadata for an external research output.

    This is the schema we ask the LLM to return. Fields are optional because
    some pages do not surface every value (e.g. press releases without a
    visible author list). The ingestion service decides whether the row can
    be inserted given how many fields were filled in.
    """

    reasoning: str = Field(
        default="",
        description="Brief notes on where each field was found on the page.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Page title as it should appear in feeds.",
    )
    abstract: Optional[str] = Field(
        default=None,
        description=(
            "Short summary of the resource. Aim for 2-5 sentences extracted "
            "or condensed from the page lede or executive summary."
        ),
    )
    authors: List[str] = Field(
        default_factory=list,
        description=(
            "Individual human authors only (no organizations). May be empty "
            "for organization-authored posts."
        ),
    )
    date_published: Optional[date] = Field(
        default=None,
        description=(
            "Original publication date in ISO YYYY-MM-DD format. Use the "
            "earliest credible date the page exposes; omit if unknown."
        ),
    )
    github_repository_urls: List[str] = Field(
        default_factory=list,
        description=(
            "GitHub repositories the page links to as code releases or "
            "official implementations."
        ),
    )
    hf_artifact_urls: List[str] = Field(
        default_factory=list,
        description=("Hugging Face model, dataset, or space URLs the page links to."),
    )


_PROMPT = """You are an extraction assistant that converts a webpage about
an AI/ML release (technical report, blog post, model card, or vendor
announcement) into a structured JSON object.

Use only information that is clearly present on the page. Do not invent
facts. If a field is not on the page, leave it null/empty.

Return JSON matching the provided schema. Specifically:

- title: the headline/title of the page.
- abstract: 2-5 sentence summary; prefer the lede or TL;DR from the page.
- authors: list of HUMAN authors only. Do NOT include organization names
  (e.g. omit "Anthropic", "Zyphra", "OpenAI"). Many vendor posts list no
  human authors -- in that case return an empty list.
- date_published: ISO YYYY-MM-DD. Use the original publication date, not the
  scrape time. If only month/year is given, pick the 1st of the month. If
  truly unknown, omit.
- github_repository_urls: links to github.com repositories the page presents
  as official code for the release.
- hf_artifact_urls: links to huggingface.co model/dataset/space pages.

Page URL: {url}

Page text (truncated):
---
{page_text}
---
"""


async def extract_external_resource_metadata(
    url: str,
    page_text: Optional[str] = None,
    raw_html: Optional[str] = None,
    generator: Optional[Generator] = None,
) -> ExternalResourceMetadata:
    """
    Extract structured metadata for an external resource page.

    If `page_text` is omitted, the page is fetched and converted to text. The
    extracted GitHub and HF artifact URLs are post-validated against the raw
    HTML so the LLM cannot hallucinate links that are not actually on the
    page.
    """
    if page_text is None or raw_html is None:
        fetched_html, fetched_text = await fetch_html_and_text(url)
        if raw_html is None:
            raw_html = fetched_html
        if page_text is None:
            page_text = fetched_text

    if not page_text:
        logger.warning("No text extracted from %s; returning empty metadata", url)
        return ExternalResourceMetadata()

    generator = generator or OpenRouterGenerator()
    # Many providers (e.g. Gemini) don't accept a `system` role; embed the
    # instruction prefix in the single user message instead.
    instructions = (
        "You extract structured metadata from AI/ML release pages. "
        "Return JSON conforming to the schema. Never invent values.\n\n"
    )
    messages = [
        Message(
            role="user",
            content=instructions + _PROMPT.format(url=url, page_text=page_text),
        ),
    ]

    response, _model = await generator.generate(
        messages, schema=ExternalResourceMetadata
    )

    # Some providers (notably the GoogleGenerator) return a dict rather than
    # a parsed Pydantic instance even when a schema is requested. Coerce.
    if isinstance(response, dict):
        response = ExternalResourceMetadata(**response)
    elif isinstance(response, str):
        response = ExternalResourceMetadata(**json.loads(response))

    # Defence in depth: cross-check the LLM-suggested links against the actual
    # page HTML. The LLM is instructed not to hallucinate, but trust-but-verify
    # is cheap.
    if raw_html:
        page_github = set(extract_github_urls(raw_html, base_url=url))
        page_hf = set(extract_hf_repo_urls(raw_html, base_url=url))

        kept_github = [u for u in response.github_repository_urls if u in page_github]
        if not kept_github:
            kept_github = sorted(page_github)
        response.github_repository_urls = kept_github

        kept_hf = [u for u in response.hf_artifact_urls if u in page_hf]
        if not kept_hf:
            kept_hf = sorted(page_hf)
        response.hf_artifact_urls = kept_hf

    return response


async def _main(url: str) -> None:
    metadata = await extract_external_resource_metadata(url)
    print(json.dumps(metadata.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract metadata from an external research-output page."
    )
    parser.add_argument("--url", required=True, help="Page URL to extract from")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main(args.url))
