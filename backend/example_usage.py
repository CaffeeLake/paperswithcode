#!/usr/bin/env python3
"""
Example usage of the PapersWithCode FastAPI backend.

This script demonstrates how to use the API endpoints with sample requests.
Run this after starting the server to test the functionality.
"""

import requests
import json
from typing import Dict, Any


class PapersWithCodeAPI:
    """Simple client for the PapersWithCode API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/api/v1"
    
    def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make a GET request to the API."""
        url = f"{self.api_base}{endpoint}"
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the API is healthy."""
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def get_papers(self, page: int = 1, page_size: int = 10, **kwargs) -> Dict[str, Any]:
        """Get paginated list of papers."""
        params = {"page": page, "page_size": page_size, **kwargs}
        return self._get("/papers/", params)
    
    def get_paper_by_id(self, paper_id: int) -> Dict[str, Any]:
        """Get a specific paper by database ID."""
        return self._get(f"/papers/{paper_id}")
    
    def get_paper_by_arxiv_id(self, arxiv_id: str, version: str = None) -> Dict[str, Any]:
        """Get a paper by ArXiv ID."""
        params = {"version": version} if version else {}
        return self._get(f"/papers/arxiv/{arxiv_id}", params)
    
    def get_paper_versions(self, arxiv_id: str) -> Dict[str, Any]:
        """Get all versions of a paper."""
        return self._get(f"/papers/arxiv/{arxiv_id}/versions")
    
    def compare_versions(self, arxiv_id: str, from_version: str, to_version: str) -> Dict[str, Any]:
        """Compare two versions of a paper."""
        return self._get(f"/papers/arxiv/{arxiv_id}/versions/{from_version}/compare/{to_version}")
    
    def search_papers(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search papers by query."""
        params = {"q": query, "limit": limit}
        return self._get("/papers/search", params)
    
    def get_recent_papers(self, limit: int = 10) -> Dict[str, Any]:
        """Get recently published papers."""
        params = {"limit": limit}
        return self._get("/papers/recent", params)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get paper statistics."""
        return self._get("/papers/stats")


def main():
    """Demonstrate API usage."""
    print("🚀 PapersWithCode API Example Usage")
    print("=" * 50)
    
    # Initialize API client
    api = PapersWithCodeAPI()
    
    try:
        # 1. Health check
        print("1. Health Check:")
        health = api.health_check()
        print(f"   Status: {health['status']}")
        print()
        
        # 2. Get recent papers
        print("2. Recent Papers:")
        recent = api.get_recent_papers(limit=3)
        for paper in recent:
            print(f"   - {paper['title'][:60]}... ({paper['arxiv_id']})")
        print()
        
        # 3. Search papers
        print("3. Search Papers (query: 'transformer'):")
        search_results = api.search_papers("transformer", limit=3)
        for paper in search_results:
            print(f"   - {paper['title'][:60]}... ({paper['arxiv_id']})")
        print()
        
        # 4. Get papers with pagination
        print("4. Paginated Papers:")
        papers = api.get_papers(page=1, page_size=5)
        print(f"   Total papers: {papers['count']}")
        print(f"   Papers on this page: {len(papers['results'])}")
        print(f"   Next page: {papers['next_page']}")
        print()
        
        # 5. Get specific paper (if any papers exist)
        if papers['results']:
            first_paper = papers['results'][0]
            print("5. Specific Paper Details:")
            print(f"   ID: {first_paper['id']}")
            print(f"   Title: {first_paper['title'][:80]}...")
            print(f"   Authors: {', '.join(first_paper['authors'][:3])}...")
            print(f"   ArXiv ID: {first_paper['arxiv_id']}")
            print(f"   Version: {first_paper['version']}")
            print()
            
            # 6. Get paper versions (if it has an ArXiv ID)
            if first_paper['arxiv_id']:
                print("6. Paper Versions:")
                try:
                    versions = api.get_paper_versions(first_paper['arxiv_id'])
                    print(f"   Total versions: {versions['total_versions']}")
                    for version in versions['versions'][:3]:
                        print(f"   - {version['version']}: {version['title'][:50]}...")
                except requests.exceptions.HTTPError as e:
                    print(f"   No versions found or error: {e}")
                print()
        
        # 7. Statistics
        print("7. Database Statistics:")
        stats = api.get_stats()
        print(f"   Total papers: {stats['total_papers']}")
        print(f"   Latest versions only: {stats['latest_versions_only']}")
        if stats['papers_by_year']:
            print(f"   Recent years: {[f\"{year['year']}: {year['count']}\" for year in stats['papers_by_year'][:5]]}")
        print()
        
        print("✅ All API endpoints working correctly!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the API server.")
        print("   Make sure the server is running: python backend/run_server.py")
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print("   Check the server logs for more details.")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
