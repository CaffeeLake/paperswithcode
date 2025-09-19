"""
Data Quality Analysis Script

This script compares the current high-quality Repository table data with the
paperswithcode links-between-papers-and-code.json file to assess data quality
and coverage.

The goal is to determine:
1. How many of our current repository entries appear in the JSON file
2. How many match exactly (same paper + same repo URL)
3. Quality indicators of the JSON data based on our verified entries

📊 USAGE:
  python analyze_data_quality.py
"""

import sys
import json
import logging
from pathlib import Path
from typing import List, Dict
import re

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent.parent.parent.parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

from backend.database.connection import get_database_session
from sqlalchemy import text
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DataQualityAnalyzer:
    """
    Analyzes the quality of paperswithcode JSON data by comparing it
    with our current high-quality Repository table entries.
    """

    def __init__(self):
        self.json_file_path = (
            project_root / "data" / "links-between-papers-and-code.json"
        )
        self.stats = {
            "current_repos_count": 0,
            "json_entries_count": 0,
            "exact_matches": 0,
            "paper_matches": 0,
            "repo_matches": 0,
            "no_matches": 0,
            "json_entries_with_arxiv": 0,
            "json_entries_official": 0,
            "current_repos_official": 0,
        }
        self.matches = []
        self.mismatches = []

    def normalize_github_url(self, url: str) -> str:
        """Normalize GitHub URL for comparison."""
        if not url:
            return ""

        # Remove trailing slashes, convert to lowercase
        url = url.rstrip("/").lower()

        # Ensure it starts with https://github.com
        if url.startswith("http://github.com"):
            url = url.replace("http://github.com", "https://github.com")
        elif not url.startswith("https://github.com"):
            if url.startswith("github.com"):
                url = "https://" + url
            else:
                return url  # Not a GitHub URL

        return url

    def extract_arxiv_id(self, arxiv_id: str) -> str:
        """Extract base ArXiv ID without version."""
        if not arxiv_id:
            return ""

        # Remove version suffix (e.g., "1234.5678v2" -> "1234.5678")
        return re.sub(r"v\d+$", "", arxiv_id)

    def load_current_repositories(self, db: Session) -> List[Dict]:
        """Load current repository entries from database."""
        logger.info("Loading current repository entries from database...")

        try:
            result = db.execute(
                text("""
                SELECT
                    r.id,
                    r.paper_id,
                    r.url,
                    r.owner,
                    r.name,
                    r.is_official,
                    p.arxiv_id,
                    p.title,
                    p.version
                FROM repositories r
                JOIN papers p ON r.paper_id = p.id
                ORDER BY r.id
            """)
            )

            repos = []
            for row in result:
                repos.append(
                    {
                        "id": row.id,
                        "paper_id": row.paper_id,
                        "url": self.normalize_github_url(row.url),
                        "owner": row.owner,
                        "name": row.name,
                        "is_official": row.is_official,
                        "arxiv_id": self.extract_arxiv_id(row.arxiv_id),
                        "title": row.title,
                        "version": row.version,
                    }
                )

            self.stats["current_repos_count"] = len(repos)
            self.stats["current_repos_official"] = sum(
                1 for r in repos if r["is_official"]
            )

            logger.info(f"Loaded {len(repos)} repository entries from database")
            logger.info(
                f"Official repositories: {self.stats['current_repos_official']}"
            )

            return repos

        except Exception as e:
            logger.error(f"Error loading repository data: {e}")
            return []

    def load_json_data(self) -> List[Dict]:
        """Load paperswithcode JSON data."""
        logger.info(f"Loading JSON data from {self.json_file_path}...")

        try:
            with open(self.json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Process and normalize the data
            processed_data = []
            for entry in data:
                if entry.get("paper_arxiv_id") and entry.get("repo_url"):
                    processed_entry = {
                        "paper_arxiv_id": self.extract_arxiv_id(
                            entry["paper_arxiv_id"]
                        ),
                        "repo_url": self.normalize_github_url(entry["repo_url"]),
                        "paper_title": entry.get("paper_title", ""),
                        "is_official": entry.get("is_official", False),
                        "mentioned_in_paper": entry.get("mentioned_in_paper", False),
                        "mentioned_in_github": entry.get("mentioned_in_github", False),
                        "framework": entry.get("framework", "none"),
                    }
                    processed_data.append(processed_entry)

            self.stats["json_entries_count"] = len(data)
            self.stats["json_entries_with_arxiv"] = len(processed_data)
            self.stats["json_entries_official"] = sum(
                1 for e in processed_data if e["is_official"]
            )

            logger.info(f"Loaded {len(data)} total JSON entries")
            logger.info(f"Entries with ArXiv ID and repo URL: {len(processed_data)}")
            logger.info(
                f"Official entries in JSON: {self.stats['json_entries_official']}"
            )

            return processed_data

        except Exception as e:
            logger.error(f"Error loading JSON data: {e}")
            return []

    def find_matches(self, current_repos: List[Dict], json_data: List[Dict]):
        """Find matches between current repos and JSON data."""
        logger.info("Analyzing matches between current repositories and JSON data...")

        # Create lookup dictionaries for efficient matching
        json_by_arxiv = {}
        json_by_repo = {}
        json_by_both = {}

        for entry in json_data:
            arxiv_id = entry["paper_arxiv_id"]
            repo_url = entry["repo_url"]

            # Index by ArXiv ID
            if arxiv_id not in json_by_arxiv:
                json_by_arxiv[arxiv_id] = []
            json_by_arxiv[arxiv_id].append(entry)

            # Index by repo URL
            if repo_url not in json_by_repo:
                json_by_repo[repo_url] = []
            json_by_repo[repo_url].append(entry)

            # Index by both (exact match)
            key = (arxiv_id, repo_url)
            if key not in json_by_both:
                json_by_both[key] = []
            json_by_both[key].append(entry)

        # Check each current repository against JSON data
        for repo in current_repos:
            arxiv_id = repo["arxiv_id"]
            repo_url = repo["url"]
            match_key = (arxiv_id, repo_url)

            match_type = None
            json_matches = []

            # Check for exact match (same paper + same repo)
            if match_key in json_by_both:
                match_type = "exact"
                json_matches = json_by_both[match_key]
                self.stats["exact_matches"] += 1

            # Check for paper match (same ArXiv ID, different repo)
            elif arxiv_id in json_by_arxiv:
                match_type = "paper_only"
                json_matches = json_by_arxiv[arxiv_id]
                self.stats["paper_matches"] += 1

            # Check for repo match (same repo URL, different paper)
            elif repo_url in json_by_repo:
                match_type = "repo_only"
                json_matches = json_by_repo[repo_url]
                self.stats["repo_matches"] += 1

            # No match found
            else:
                match_type = "no_match"
                self.stats["no_matches"] += 1

            # Store the match information
            match_info = {
                "current_repo": repo,
                "match_type": match_type,
                "json_matches": json_matches,
                "json_match_count": len(json_matches),
            }

            if match_type == "exact":
                self.matches.append(match_info)
            else:
                self.mismatches.append(match_info)

    def print_analysis_results(self):
        """Print detailed analysis results."""
        print("\n" + "=" * 80)
        print("DATA QUALITY ANALYSIS RESULTS")
        print("=" * 80)

        print("\n📊 OVERVIEW:")
        print(
            f"  Current Repository entries (high-quality): {self.stats['current_repos_count']:,}"
        )
        print(f"  JSON entries total: {self.stats['json_entries_count']:,}")
        print(
            f"  JSON entries with ArXiv ID + repo URL: {self.stats['json_entries_with_arxiv']:,}"
        )

        print("\n🎯 MATCH ANALYSIS:")
        print(
            f"  Exact matches (same paper + same repo): {self.stats['exact_matches']:,}"
        )
        print(
            f"  Paper matches (same ArXiv ID, different repo): {self.stats['paper_matches']:,}"
        )
        print(
            f"  Repo matches (same repo URL, different paper): {self.stats['repo_matches']:,}"
        )
        print(f"  No matches found: {self.stats['no_matches']:,}")

        # Calculate percentages
        total_current = self.stats["current_repos_count"]
        if total_current > 0:
            exact_pct = (self.stats["exact_matches"] / total_current) * 100
            paper_pct = (self.stats["paper_matches"] / total_current) * 100
            repo_pct = (self.stats["repo_matches"] / total_current) * 100
            no_match_pct = (self.stats["no_matches"] / total_current) * 100

            print("\n📈 MATCH PERCENTAGES:")
            print(f"  Exact matches: {exact_pct:.1f}%")
            print(f"  Paper matches: {paper_pct:.1f}%")
            print(f"  Repo matches: {repo_pct:.1f}%")
            print(f"  No matches: {no_match_pct:.1f}%")

        print("\n🏆 OFFICIAL STATUS:")
        print(
            f"  Current repos marked as official: {self.stats['current_repos_official']:,}"
        )
        print(
            f"  JSON entries marked as official: {self.stats['json_entries_official']:,}"
        )

        # Show some examples
        print("\n✅ EXACT MATCH EXAMPLES (first 5):")
        for i, match in enumerate(self.matches[:5]):
            repo = match["current_repo"]
            json_match = match["json_matches"][0]  # Take first match
            print(f"  {i + 1}. ArXiv: {repo['arxiv_id']} | Repo: {repo['url']}")
            print(f"     Title: {repo['title'][:60]}...")
            print(
                f"     Official - Current: {repo['is_official']}, JSON: {json_match['is_official']}"
            )

        print("\n❌ NO MATCH EXAMPLES (first 5):")
        no_matches = [m for m in self.mismatches if m["match_type"] == "no_match"]
        for i, mismatch in enumerate(no_matches[:5]):
            repo = mismatch["current_repo"]
            print(f"  {i + 1}. ArXiv: {repo['arxiv_id']} | Repo: {repo['url']}")
            print(f"     Title: {repo['title'][:60]}...")

        print("\n🔍 PAPER MATCH EXAMPLES (first 3):")
        paper_matches = [m for m in self.mismatches if m["match_type"] == "paper_only"]
        for i, mismatch in enumerate(paper_matches[:3]):
            repo = mismatch["current_repo"]
            json_matches = mismatch["json_matches"]
            print(
                f"  {i + 1}. ArXiv: {repo['arxiv_id']} (found {len(json_matches)} different repos in JSON)"
            )
            print(f"     Current repo: {repo['url']}")
            print(
                f"     JSON repos: {', '.join([m['repo_url'] for m in json_matches[:3]])}"
            )

        # Data quality assessment
        coverage = (
            (self.stats["exact_matches"] / total_current) * 100
            if total_current > 0
            else 0
        )

        print("\n🎯 DATA QUALITY ASSESSMENT:")
        print(f"  Coverage: {coverage:.1f}% of high-quality repos found in JSON")

        if coverage >= 80:
            quality = "EXCELLENT"
        elif coverage >= 60:
            quality = "GOOD"
        elif coverage >= 40:
            quality = "MODERATE"
        else:
            quality = "POOR"

        print(f"  Quality Rating: {quality}")

        if coverage < 50:
            print("\n⚠️  WARNING: Low coverage suggests significant noise in JSON data")

        print("=" * 80)

    def run_analysis(self):
        """Run the complete data quality analysis."""
        logger.info("Starting data quality analysis...")

        # Get database session
        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            # Load current repository data
            current_repos = self.load_current_repositories(db)
            if not current_repos:
                logger.error("No current repository data found")
                return

            # Load JSON data
            json_data = self.load_json_data()
            if not json_data:
                logger.error("No JSON data found")
                return

            # Find matches
            self.find_matches(current_repos, json_data)

            # Print results
            self.print_analysis_results()

        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            raise
        finally:
            db.close()


def main():
    """Main function."""
    analyzer = DataQualityAnalyzer()
    analyzer.run_analysis()


if __name__ == "__main__":
    main()
