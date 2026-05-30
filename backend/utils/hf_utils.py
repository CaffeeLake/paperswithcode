import re
import aiohttp
import asyncio
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

from huggingface_hub.utils import build_hf_headers


HfArtifactKind = Literal["model", "dataset", "space"]


_HF_NON_ARTIFACT_PATHS = {
    "",
    "api",
    "blog",
    "chat",
    "collections",
    "community",
    "docs",
    "enterprise",
    "join",
    "learn",
    "login",
    "models",
    "new",
    "papers",
    "posts",
    "pricing",
    "settings",
    "signup",
    "spaces",
    "tasks",
    "tos",
    "trending",
}


def normalize_hf_artifact_url(url: str) -> Optional[str]:
    """
    Normalize a Hugging Face artifact URL into a canonical, render-ready form.

    Returns the URL with scheme forced to https, host forced to
    `huggingface.co`, no query string, no fragment, and any trailing slash
    stripped. Returns None if the URL does not look like an HF artifact URL.
    """
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = "https://" + candidate

    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower()
    if host in {"www.huggingface.co", "hf.co", "www.hf.co"}:
        host = "huggingface.co"
    if host != "huggingface.co":
        return None

    path = parsed.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    if not path or path == "/":
        return None

    return urlunparse(("https", host, path, "", "", ""))


def normalize_hf_artifact_bucket(
    urls: list[str],
    expected_kind: HfArtifactKind,
    *,
    bucket_label: str,
) -> list[str]:
    """Normalize and validate a list of HF artifact URLs for one bucket.

    Raises ``ValueError`` when a URL is invalid or classified into a different
    artifact kind than ``expected_kind``.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw_url in urls or []:
        normalized = normalize_hf_artifact_url(raw_url)
        if normalized is None:
            raise ValueError(f"Invalid Hugging Face {bucket_label} URL: {raw_url!r}")
        kind = classify_hf_artifact_url(normalized)
        if kind != expected_kind:
            raise ValueError(
                f"URL {raw_url!r} is not a Hugging Face {bucket_label} link"
            )
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def normalize_hf_artifact_payload(
    hf_models: list[str],
    hf_datasets: list[str],
    hf_spaces: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Normalize three HF artifact URL lists for storage on ``papers``."""
    models = normalize_hf_artifact_bucket(hf_models, "model", bucket_label="model")
    datasets = normalize_hf_artifact_bucket(
        hf_datasets, "dataset", bucket_label="dataset"
    )
    spaces = normalize_hf_artifact_bucket(hf_spaces, "space", bucket_label="space")
    return models, datasets, spaces


def classify_hf_artifact_url(url: str) -> Optional[HfArtifactKind]:
    """
    Determine whether a Hugging Face URL points to a model, dataset, or space.

    Returns None for URLs that do not look like HF artifact URLs (e.g.
    profile, papers, blog, or arxiv filter URLs).
    """
    normalized = normalize_hf_artifact_url(url)
    if normalized is None:
        return None

    path = urlparse(normalized).path.lstrip("/")
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        return None

    head = segments[0].lower()
    if head == "datasets" and len(segments) >= 2:
        return "dataset"
    if head == "spaces" and len(segments) >= 2:
        return "space"
    if head in _HF_NON_ARTIFACT_PATHS:
        return None
    # `huggingface.co/<namespace>/<name>` is a model; bare `huggingface.co/<name>`
    # is a user/org profile and is not considered an artifact link.
    if len(segments) >= 2:
        return "model"
    return None


async def get_user_organizations(username: str) -> list[str]:
    """
    Get all organizations that a Hugging Face user belongs to by parsing their HF profile page.

    Args:
        username (str): The Hugging Face username

    Returns:
        list[str]: List of organization names the user belongs to

    Example:
        >>> orgs = await get_user_organizations("phython96")
        >>> print(orgs)  # ["CraftJarvis"]
    """
    url = f"https://huggingface.co/{username}"

    async def _fetch_profile():
        headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                return await response.text()

    try:
        # Shield from cancellation to prevent cancel scope propagation
        html_content = await asyncio.shield(_fetch_profile())

        organizations = []

        # Look for the Organizations section in the HTML
        # The HTML structure typically has an Organizations heading followed by organization links
        # Pattern 1: Look for text "Organizations" followed by links
        orgs_section_pattern = r"(?i)organizations.*?(?=<h[1-6]|$)"
        orgs_section_match = re.search(orgs_section_pattern, html_content, re.DOTALL)

        if orgs_section_match:
            orgs_section = orgs_section_match.group(0)
            # Look for organization profile links in this section
            # Organizations typically appear as href="/{org_name}" links
            org_links_pattern = r'href="/([^/\s"]+)"'
            org_matches = re.findall(org_links_pattern, orgs_section)

            # Filter out common non-organization paths and the username itself
            for org in org_matches:
                if (
                    org != username
                    and org
                    not in [
                        "models",
                        "datasets",
                        "spaces",
                        "papers",
                        "docs",
                        "settings",
                        "join",
                        "pricing",
                        "enterprise",
                        "community",
                        "login",
                        "signup",
                    ]
                    and not org.startswith("http")
                    and len(org) > 1
                ):
                    organizations.append(org)

        # Fallback pattern: Look for organization-style links throughout the page
        if not organizations:
            # Look for links that could be organizations (simple names without special characters)
            all_links_pattern = r'href="/([a-zA-Z0-9][a-zA-Z0-9_-]*)"'
            all_matches = re.findall(all_links_pattern, html_content)

            # Count occurrences and filter likely organization names
            link_counts = {}
            for link in all_matches:
                if (
                    link != username
                    and link
                    not in [
                        "models",
                        "datasets",
                        "spaces",
                        "papers",
                        "docs",
                        "settings",
                        "join",
                        "spaces",
                        "new",
                        "pricing",
                        "enterprise",
                        "community",
                        "login",
                        "signup",
                    ]
                    and not link.startswith("http")
                    and len(link) > 1
                ):
                    link_counts[link] = link_counts.get(link, 0) + 1

            # Organizations typically appear multiple times on a profile page
            # (in different sections like "Recent Activity", etc.)
            for link, count in link_counts.items():
                if count >= 2:  # Appears multiple times, likely an organization
                    organizations.append(link)

        # Remove duplicates while preserving order
        seen = set()
        unique_orgs = []
        for org in organizations:
            if org not in seen:
                seen.add(org)
                unique_orgs.append(org)

        return unique_orgs

    except asyncio.CancelledError:
        print(f"Request cancelled while fetching organizations for user {username}")
        return []
    except Exception as e:
        print(f"Error fetching organizations for user {username}: {e}")
        return []


if __name__ == "__main__":
    orgs = asyncio.run(get_user_organizations("nielsr"))
    print(orgs)
