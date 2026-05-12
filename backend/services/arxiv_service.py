"""
ArXiv API service for fetching paper metadata and PDFs.

This service handles interactions with the ArXiv API to:
- Fetch paper metadata by ArXiv ID
- Get PDF URLs with proper version handling
- Respect ArXiv rate limits (3 seconds between requests)
- Handle ArXiv API responses and errors gracefully
"""

import asyncio
from email.utils import parsedate_to_datetime
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx

from backend.config import get_settings

# Configure logging
logger = logging.getLogger(__name__)

# ArXiv API configuration
ARXIV_API_BASE_URL = "https://export.arxiv.org/api/query"
ARXIV_PDF_BASE_URL = "https://arxiv.org/pdf"
REQUEST_TIMEOUT = 30.0
RATE_LIMIT_DELAY = 3.0  # ArXiv requires 3 seconds between requests
MAX_RETRIES = 3
PDF_429_FALLBACK_DELAY = 60.0


@dataclass
class ArxivPaperMetadata:
    """ArXiv paper metadata from API response."""

    arxiv_id: str
    version: str
    title: str
    abstract: str
    authors: List[str]
    published: datetime
    updated: datetime
    pdf_url: str
    abs_url: str
    categories: List[str]
    primary_category: str
    success: bool = True
    error_message: Optional[str] = None


class ArxivService:
    """
    Service for interacting with the ArXiv API.

    Handles rate limiting, retries, and proper error handling
    for all ArXiv API interactions.
    """

    def __init__(self):
        """Initialize the ArXiv service."""
        self.settings = get_settings()
        self.last_request_time = 0.0
        self.headers = {
            "User-Agent": "PapersWithCode-ArxivService/1.0 (https://paperswithcode.ai)"
        }

    async def _rate_limit(self) -> None:
        """
        Ensure proper rate limiting between ArXiv API requests.
        ArXiv requires at least 3 seconds between requests.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < RATE_LIMIT_DELAY:
            sleep_time = RATE_LIMIT_DELAY - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def _build_direct_pdf_url(self, arxiv_id: str, version: str) -> str:
        clean_arxiv_id = arxiv_id.replace("arXiv:", "").strip()
        clean_arxiv_id = clean_arxiv_id.removesuffix(".pdf")
        clean_arxiv_id = re.sub(r"v\d+$", "", clean_arxiv_id)
        clean_version = version.strip()
        return f"{ARXIV_PDF_BASE_URL}/{clean_arxiv_id}{clean_version}"

    def _get_429_retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    return max(
                        0.0,
                        (retry_at - datetime.now(timezone.utc)).total_seconds(),
                    )
                except (TypeError, ValueError):
                    pass

        return PDF_429_FALLBACK_DELAY * (2**attempt)

    async def _make_request(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        """
        Make a rate-limited request to the ArXiv API.

        Args:
            url: API endpoint URL
            params: Query parameters

        Returns:
            HTTP response

        Raises:
            httpx.HTTPError: If request fails after retries
        """
        await self._rate_limit()

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(
                        url, params=params, headers=self.headers
                    )
                    response.raise_for_status()
                    return response

                except httpx.HTTPError as e:
                    if attempt == MAX_RETRIES - 1:
                        logger.error(
                            f"ArXiv API request failed after {MAX_RETRIES} attempts: {e}"
                        )
                        raise

                    logger.warning(
                        f"ArXiv API request failed (attempt {attempt + 1}): {e}"
                    )
                    await asyncio.sleep(2**attempt)  # Exponential backoff

    def _parse_arxiv_response(
        self, xml_content: str, requested_arxiv_id: str
    ) -> ArxivPaperMetadata:
        """
        Parse ArXiv API XML response into structured metadata.

        Args:
            xml_content: XML response from ArXiv API
            requested_arxiv_id: The ArXiv ID that was requested

        Returns:
            ArxivPaperMetadata object
        """
        try:
            root = ET.fromstring(xml_content)

            # Find entries in the response
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")

            if not entries:
                return ArxivPaperMetadata(
                    arxiv_id=requested_arxiv_id,
                    version="",
                    title="",
                    abstract="",
                    authors=[],
                    published=datetime.now(),
                    updated=datetime.now(),
                    pdf_url="",
                    abs_url="",
                    categories=[],
                    primary_category="",
                    success=False,
                    error_message="Paper not found in ArXiv",
                )

            entry = entries[0]

            # Extract basic information
            title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
            title = (
                title_elem.text.strip().replace("\n", " ")
                if title_elem is not None
                else ""
            )

            summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary")
            abstract = (
                summary_elem.text.strip().replace("\n", " ")
                if summary_elem is not None
                else ""
            )

            # Extract dates
            published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
            published = (
                datetime.fromisoformat(published_elem.text.replace("Z", "+00:00"))
                if published_elem is not None
                else datetime.now()
            )

            updated_elem = entry.find("{http://www.w3.org/2005/Atom}updated")
            updated = (
                datetime.fromisoformat(updated_elem.text.replace("Z", "+00:00"))
                if updated_elem is not None
                else published
            )

            # Extract ArXiv ID and version from the entry ID
            id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
            full_id = (
                id_elem.text.split("/")[-1]
                if id_elem is not None
                else requested_arxiv_id
            )

            # Parse ArXiv ID and version (e.g., "1810.04805v2" -> "1810.04805", "v2")
            arxiv_match = re.match(r"(\d+\.\d+)(v\d+)?", full_id)
            if arxiv_match:
                arxiv_id = arxiv_match.group(1)
                version = arxiv_match.group(2) or "v1"
            else:
                arxiv_id = requested_arxiv_id
                version = "v1"

            # Extract authors
            authors = []
            author_elements = entry.findall("{http://www.w3.org/2005/Atom}author")
            for author_elem in author_elements:
                name_elem = author_elem.find("{http://www.w3.org/2005/Atom}name")
                if name_elem is not None:
                    authors.append(name_elem.text.strip())

            # Extract categories
            categories = []
            category_elements = entry.findall("{http://www.w3.org/2005/Atom}category")
            for cat_elem in category_elements:
                term = cat_elem.get("term")
                if term:
                    categories.append(term)

            primary_category = categories[0] if categories else ""

            # Extract URLs
            pdf_url = ""
            abs_url = ""

            link_elements = entry.findall("{http://www.w3.org/2005/Atom}link")
            for link_elem in link_elements:
                link_type = link_elem.get("type")
                href = link_elem.get("href", "")

                if link_type == "application/pdf":
                    pdf_url = href
                elif link_elem.get("rel") == "alternate" and link_type == "text/html":
                    abs_url = href

            return ArxivPaperMetadata(
                arxiv_id=arxiv_id,
                version=version,
                title=title,
                abstract=abstract,
                authors=authors,
                published=published,
                updated=updated,
                pdf_url=pdf_url,
                abs_url=abs_url,
                categories=categories,
                primary_category=primary_category,
                success=True,
            )

        except Exception as e:
            logger.error(f"Error parsing ArXiv response: {e}")
            return ArxivPaperMetadata(
                arxiv_id=requested_arxiv_id,
                version="",
                title="",
                abstract="",
                authors=[],
                published=datetime.now(),
                updated=datetime.now(),
                pdf_url="",
                abs_url="",
                categories=[],
                primary_category="",
                success=False,
                error_message=f"Error parsing response: {str(e)}",
            )

    async def get_paper_metadata(self, arxiv_id: str) -> ArxivPaperMetadata:
        """
        Fetch paper metadata from ArXiv API.

        Args:
            arxiv_id: ArXiv ID (e.g., "1810.04805")

        Returns:
            ArxivPaperMetadata object with paper information
        """
        try:
            # Clean the ArXiv ID
            clean_arxiv_id = arxiv_id.replace("arXiv:", "").strip()

            logger.debug(f"Fetching ArXiv metadata for: {clean_arxiv_id}")

            # Make API request
            response = await self._make_request(
                ARXIV_API_BASE_URL, params={"id_list": clean_arxiv_id}
            )

            # Parse response
            metadata = self._parse_arxiv_response(response.text, clean_arxiv_id)

            if metadata.success:
                logger.info(
                    f"Successfully fetched metadata for ArXiv ID: {clean_arxiv_id}"
                )
            else:
                logger.warning(
                    f"Failed to fetch metadata for ArXiv ID: {clean_arxiv_id} - {metadata.error_message}"
                )

            return metadata

        except Exception as e:
            logger.error(f"Error fetching ArXiv metadata for {arxiv_id}: {e}")
            return ArxivPaperMetadata(
                arxiv_id=arxiv_id,
                version="",
                title="",
                abstract="",
                authors=[],
                published=datetime.now(),
                updated=datetime.now(),
                pdf_url="",
                abs_url="",
                categories=[],
                primary_category="",
                success=False,
                error_message=str(e),
            )

    async def get_pdf_url(
        self, arxiv_id: str, version: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the PDF URL for a specific ArXiv paper and version.

        Args:
            arxiv_id: ArXiv ID (e.g., "1810.04805")
            version: Specific version (e.g., "v2"), if None gets latest

        Returns:
            PDF URL or None if not found
        """
        try:
            metadata = await self.get_paper_metadata(arxiv_id)

            if not metadata.success or not metadata.pdf_url:
                return None

            pdf_url = metadata.pdf_url

            # If specific version requested and it's different from what we got
            if version and version != metadata.version:
                # Modify URL to get specific version
                # Remove existing version if present, then add requested version
                import re

                # Remove existing version pattern (e.g., v1, v2, etc.)
                pdf_url = re.sub(r"v\d+", "", pdf_url)
                # Add requested version before .pdf extension
                if pdf_url.endswith(".pdf"):
                    pdf_url = pdf_url.replace(".pdf", f"{version}.pdf")
                else:
                    pdf_url = f"{pdf_url}{version}.pdf"

            return pdf_url

        except Exception as e:
            logger.error(f"Error getting PDF URL for {arxiv_id}: {e}")
            return None

    async def download_pdf(
        self, arxiv_id: str, version: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Download PDF content for an ArXiv paper.

        Args:
            arxiv_id: ArXiv ID (e.g., "1810.04805")
            version: Specific version (e.g., "v2"), if None gets latest

        Returns:
            PDF content as bytes or None if download fails
        """
        try:
            pdf_url = (
                self._build_direct_pdf_url(arxiv_id, version)
                if version
                else await self.get_pdf_url(arxiv_id, version)
            )

            if not pdf_url:
                logger.warning(f"No PDF URL found for ArXiv ID: {arxiv_id}")
                return None

            logger.debug(f"Downloading PDF from: {pdf_url}")

            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, follow_redirects=True
            ) as client:
                for attempt in range(MAX_RETRIES):
                    # Rate limit before each PDF download attempt.
                    await self._rate_limit()

                    response = await client.get(pdf_url, headers=self.headers)

                    if response.status_code == 429:
                        if attempt == MAX_RETRIES - 1:
                            logger.error(
                                "ArXiv PDF download got 429 after %d attempts for %s",
                                MAX_RETRIES,
                                arxiv_id,
                            )
                            return None

                        retry_delay = self._get_429_retry_delay(response, attempt)
                        logger.warning(
                            "ArXiv PDF download got 429 for %s; sleeping %.1fs before retry %d/%d",
                            arxiv_id,
                            retry_delay,
                            attempt + 2,
                            MAX_RETRIES,
                        )
                        await asyncio.sleep(retry_delay)
                        continue

                    # Check if we got HTML (reCAPTCHA) instead of PDF
                    content_type = response.headers.get("content-type", "")
                    if "text/html" in content_type:
                        logger.warning(
                            f"Got HTML response (likely reCAPTCHA) for PDF download: {arxiv_id}"
                        )
                        return None

                    response.raise_for_status()

                    # Verify we got PDF content
                    content = response.content
                    if not content.startswith(b"%PDF"):
                        logger.warning(
                            f"Downloaded content is not a valid PDF for ArXiv ID: {arxiv_id}"
                        )
                        return None

                    logger.info(
                        f"Successfully downloaded PDF for ArXiv ID: {arxiv_id} ({len(content)} bytes)"
                    )
                    return content

        except Exception as e:
            logger.error(f"Error downloading PDF for {arxiv_id}: {e}")
            return None
