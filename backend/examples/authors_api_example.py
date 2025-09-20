"""
Example usage of the Authors API endpoints.

This script demonstrates how to use the new Authors API endpoints
to retrieve author information and their associated papers.
"""

import asyncio
import httpx
from typing import Optional


class AuthorsAPIClient:
    """Simple client for the Authors API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    async def get_authors(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        hf_users_only: bool = False,
        order_by: str = "paper_count",
        order_dir: str = "desc",
    ):
        """Get list of authors with filtering options."""
        params = {
            "page": page,
            "page_size": page_size,
            "order_by": order_by,
            "order_dir": order_dir,
            "hf_users_only": hf_users_only,
        }

        if search:
            params["search"] = search

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/authors/", params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_author(self, author_id: str):
        """Get specific author by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/authors/{author_id}")
            response.raise_for_status()
            return response.json()

    async def get_author_papers(
        self,
        author_id: str,
        page: int = 1,
        page_size: int = 50,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
    ):
        """Get papers by specific author."""
        params = {
            "page": page,
            "page_size": page_size,
            "latest_only": latest_only,
            "order_by": order_by,
            "order_dir": order_dir,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/authors/{author_id}/papers", params=params
            )
            response.raise_for_status()
            return response.json()

    async def search_authors(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        hf_users_only: bool = False,
    ):
        """Search authors by name or username."""
        params = {
            "q": query,
            "page": page,
            "page_size": page_size,
            "hf_users_only": hf_users_only,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/authors/search", params=params
            )
            response.raise_for_status()
            return response.json()


async def main():
    """Demonstrate Authors API usage."""
    client = AuthorsAPIClient()

    print("🔍 Authors API Examples")
    print("=" * 50)

    try:
        # Example 1: Get top authors by paper count
        print("\n1. Top 10 authors by paper count:")
        authors_response = await client.get_authors(
            page_size=10, order_by="paper_count", order_dir="desc"
        )

        print(f"Total authors: {authors_response['count']}")
        for i, author in enumerate(authors_response["results"][:5], 1):
            hf_info = (
                f" (HF: @{author['hf_username']})" if author["hf_username"] else ""
            )
            print(
                f"  {i}. {author['full_name']}{hf_info} - {author['paper_count']} papers"
            )

        # Example 2: Get specific author details
        if authors_response["results"]:
            first_author = authors_response["results"][0]
            author_id = first_author["id"]

            print(
                f"\n2. Details for author {first_author['full_name']} (ID: {author_id}):"
            )
            author_details = await client.get_author(author_id)

            print(f"  Name: {author_details['full_name']}")
            print(f"  Papers: {author_details['paper_count']}")
            if author_details["hf_username"]:
                print(f"  Hugging Face: @{author_details['hf_username']}")
                print(f"  HF Pro: {'Yes' if author_details['hf_is_pro'] else 'No'}")

            # Example 3: Get author's papers
            print(f"\n3. Recent papers by {author_details['full_name']}:")
            papers_response = await client.get_author_papers(
                author_id=author_id,
                page_size=5,
                order_by="date_published",
                order_dir="desc",
            )

            print(f"Total papers: {papers_response['count']}")
            for i, paper in enumerate(papers_response["results"], 1):
                published = paper["published"] or "Unknown date"
                print(f"  {i}. {paper['title'][:80]}...")
                print(f"     ArXiv: {paper['arxiv_id']} | Published: {published}")

        # Example 4: Search for authors
        print("\n4. Search for authors with 'neural' in their name:")
        search_response = await client.search_authors(query="neural", page_size=5)

        print(f"Found {search_response['count']} authors:")
        for i, author in enumerate(search_response["results"], 1):
            hf_info = f" (@{author['hf_username']})" if author["hf_username"] else ""
            print(
                f"  {i}. {author['full_name']}{hf_info} - {author['paper_count']} papers"
            )

        # Example 5: Get only Hugging Face users
        print("\n5. Top Hugging Face users by paper count:")
        hf_authors_response = await client.get_authors(
            page_size=5, hf_users_only=True, order_by="paper_count", order_dir="desc"
        )

        print(f"Total HF authors: {hf_authors_response['count']}")
        for i, author in enumerate(hf_authors_response["results"], 1):
            pro_badge = " 🌟" if author["hf_is_pro"] else ""
            print(f"  {i}. {author['full_name']} (@{author['hf_username']}){pro_badge}")
            print(f"     Papers: {author['paper_count']}")

        # Example 6: Pagination example
        print("\n6. Pagination example (authors 11-20):")
        page2_response = await client.get_authors(
            page=2, page_size=10, order_by="paper_count", order_dir="desc"
        )

        print(f"Page 2 of {(page2_response['count'] + 9) // 10} pages")
        print(f"Previous page: {page2_response['previous_page']}")
        print(f"Next page: {page2_response['next_page']}")

        for i, author in enumerate(page2_response["results"][:3], 11):
            print(f"  {i}. {author['full_name']} - {author['paper_count']} papers")

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        print(f"❌ Request Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

    print("\n✅ Authors API examples completed!")


if __name__ == "__main__":
    print("Starting Authors API examples...")
    print("Make sure the backend server is running on http://localhost:8000")
    print()

    asyncio.run(main())
