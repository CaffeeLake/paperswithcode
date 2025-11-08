import re
import aiohttp
import asyncio

from huggingface_hub.utils import build_hf_headers


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
