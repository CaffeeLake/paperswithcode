from typing import Optional
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup

from huggingface_hub import paper_info
from huggingface_hub.utils import build_hf_headers

from backend.utils.hf_utils import get_user_organizations


GITHUB_URL_PATTERN = r"\bhttps?:\/\/github\.com[^\s]*\b"


async def get_github_and_project_page_urls_from_daily_papers(
    arxiv_id: str,
) -> tuple[str, str]:
    """
    Get the Github URL and project page URLs from the Hugging Face REST API.
    """
    github_url, project_page_url = "", ""
    if arxiv_id != "":
        try:
            headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"https://huggingface.co/api/papers/{arxiv_id}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    github_url = data.get("githubRepo", "")
                    project_page_url = data.get("projectPage", "")

        except Exception as e:
            print(f"Error getting Github URL from daily papers API: {e}")
            pass

    return github_url, project_page_url


async def find_github_url(arxiv_id: str, abstract: Optional[str] = None) -> str:
    """
    Try to extract the first matched Github URL
    from text using a regular expression.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        list: List of found GitHub URLs
    """
    if abstract is None:
        abstract = await get_abstract(arxiv_id=arxiv_id)
    match = re.search(GITHUB_URL_PATTERN, abstract)
    return match.group(0) if match else ""


async def _fetch_arxiv_page(arxiv_id: str) -> BeautifulSoup | None:
    """
    Shared function to fetch and parse an ArXiv page.

    Args:
        arxiv_id: The ArXiv identifier (e.g., "2505.17225" or "cs/0001001v1").

    Returns:
        BeautifulSoup object of the parsed HTML, or None if fetching fails.
    """
    if not arxiv_id:
        print("Error: ArXiv ID cannot be empty.")
        return None

    url = f"https://arxiv.org/abs/{arxiv_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                html_content = await response.text()
    except aiohttp.ClientError as e:
        print(f"Error fetching ArXiv page {url}: {e}")
        return None
    except asyncio.TimeoutError:
        print(f"Timeout error fetching ArXiv page {url}")
        return None

    return BeautifulSoup(html_content, "html.parser")


async def get_abstract_arxiv(arxiv_id: str) -> str | None:
    """
    Fetches the Arxiv page for a given ID and extracts the abstract asynchronously.

    Args:
        arxiv_id: The ArXiv identifier (e.g., "2505.17225" or "cs/0001001v1").

    Returns:
        The abstract text as a string, or None if fetching fails or abstract not found.
    """
    soup = await _fetch_arxiv_page(arxiv_id)
    if soup is None:
        return None

    # Primary method: Look for the blockquote containing the abstract
    abstract_blockquote = soup.find("blockquote", class_="abstract mathjax")
    if abstract_blockquote:
        full_text = abstract_blockquote.get_text(separator=" ", strip=True)
        prefix_to_remove = "Abstract:"
        if full_text.startswith(prefix_to_remove):
            abstract_text = full_text[len(prefix_to_remove) :].strip()
            return abstract_text
        else:
            # If the prefix isn't there for some reason, return the whole text of the blockquote
            # This might happen if the structure changes slightly or if there's no <span>
            return full_text  # Or return None if strict prefix matching is required

    # Fallback methods: Check meta tags
    meta_tags_to_check = [
        {"name": "citation_abstract"},
        {"property": "og:description"},
        {"name": "description"},  # This one might contain "Abstract page for..."
    ]

    for tag_attrs in meta_tags_to_check:
        meta_tag = soup.find("meta", attrs=tag_attrs)
        if meta_tag and meta_tag.get("content"):
            content = meta_tag.get("content").strip()
            # The 'description' meta tag sometimes has a prefix like "Abstract page for arXiv paper XXXXX: "
            if (
                tag_attrs.get("name") == "description"
                and "Abstract page for arXiv paper" in content
            ):
                # Try to remove the generic prefix if it's the 'description' tag
                parts = content.split(":", 1)
                if len(parts) > 1:
                    abstract_candidate = parts[1].strip()
                    # A simple heuristic: if it's long enough and doesn't seem like just a title, use it.
                    # This is to avoid picking up just "Reasoning Model is Stubborn..." from the generic description.
                    # The actual abstract from citation_abstract or og:description is usually much longer.
                    if len(abstract_candidate) > 100:  # Arbitrary length check
                        return abstract_candidate
                    # else, continue to next meta tag
            else:
                # For citation_abstract and og:description, the content is usually the direct abstract
                return content

    print(f"Abstract not found in expected locations for ArXiv ID: {arxiv_id}")
    return None


async def get_abstract_hf_hub(arxiv_id: str) -> str:
    """
    Get the abstract of a paper using the Hugging Face Hub API.
    """
    paper_details = await asyncio.to_thread(paper_info, id=arxiv_id)
    abstract = paper_details.summary
    return abstract


async def get_abstract(arxiv_id: str) -> str:
    """
    Get the abstract of a paper using the HF REST API and ArXiv API.
    """

    try:
        abstract = await get_abstract_hf_hub(arxiv_id=arxiv_id)
        if abstract is None:
            abstract = await get_abstract_arxiv(arxiv_id=arxiv_id)
    except Exception as e:
        print(f"Error getting abstract: {e}")
        abstract = "No abstract was found."

    return abstract


async def get_comments(arxiv_id: str) -> str:
    """
    Get the comments for a paper using the Hugging Face API.
    """
    comments_string = "No comments were found"
    if arxiv_id != "":
        comments_string = f"Comments at huggingface.co/papers/{arxiv_id}:"
        try:
            headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"https://huggingface.co/api/papers/{arxiv_id}?field=comments",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            comments = data.get("comments", [])
            if comments:
                current_comments_string = ""
                for idx, comment in enumerate(comments):
                    current_comments_string += f"### Comment {idx + 1} ###\n"
                    author = comment.get("author", {})
                    author_fullname = author.get("fullname", "N/A")
                    author_username = author.get("name", "N/A")
                    author_organizations = await get_user_organizations(
                        username=author_username
                    )
                    comment_data = (
                        comment.get("data", {}).get("latest", {}).get("raw", "")
                    )
                    current_comments_string += f"Author full name: {author_fullname}\n"
                    current_comments_string += (
                        f"Author Hugging Face username: {author_username}\n"
                    )
                    current_comments_string += (
                        f"Author organizations: {author_organizations}\n"
                    )
                    current_comments_string += f"Comment: {comment_data}\n\n"
                if current_comments_string:
                    comments_string = current_comments_string
                else:
                    comments_string += "\n\nNo valid comment content found."
            else:
                comments_string += "\n\nNo comments were found in API response."

        except Exception:
            comments_string += "\n\nNo comments were found (due to error)."

    return comments_string
