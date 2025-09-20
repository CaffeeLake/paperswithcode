#!/usr/bin/env python3
"""
Analyze the percentage of papers that have GitHub repositories linked.

This script connects to the PapersWithCode database and calculates:
1. Total number of papers in the database
2. Number of papers with at least one GitHub repository
3. Percentage of papers with repositories
4. Additional statistics about repository coverage
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add the backend directory to the path so we can import modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from config import get_settings  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RepositoryCoverageAnalyzer:
    """Analyze repository coverage for papers in the database."""

    def __init__(self):
        """Initialize the analyzer with database connection."""
        self.settings = get_settings()
        self.engine = create_engine(self.settings.database_url)
        self.session_local = sessionmaker(bind=self.engine)

    def analyze_coverage(self) -> Dict[str, Any]:
        """
        Analyze repository coverage and return comprehensive statistics.

        Returns:
            Dict containing coverage statistics
        """
        logger.info("Starting repository coverage analysis...")

        with self.session_local() as session:
            try:
                # Get total number of papers
                total_papers_result = session.execute(
                    text("SELECT COUNT(*) as total FROM papers")
                )
                total_papers = total_papers_result.fetchone().total

                # Get number of papers with repositories
                papers_with_repos_result = session.execute(
                    text("""
                        SELECT COUNT(DISTINCT p.id) as count
                        FROM papers p
                        INNER JOIN repositories r ON p.id = r.paper_id
                    """)
                )
                papers_with_repos = papers_with_repos_result.fetchone().count

                # Get total number of repository entries
                total_repos_result = session.execute(
                    text("SELECT COUNT(*) as total FROM repositories")
                )
                total_repos = total_repos_result.fetchone().total

                # Get papers with multiple repositories
                papers_multiple_repos_result = session.execute(
                    text("""
                        SELECT COUNT(*) as count
                        FROM (
                            SELECT p.id
                            FROM papers p
                            INNER JOIN repositories r ON p.id = r.paper_id
                            GROUP BY p.id
                            HAVING COUNT(r.id) > 1
                        ) as multi_repo_papers
                    """)
                )
                papers_multiple_repos = papers_multiple_repos_result.fetchone().count

                # Get official repositories count
                official_repos_result = session.execute(
                    text("""
                        SELECT COUNT(*) as count
                        FROM repositories
                        WHERE is_official = true
                    """)
                )
                official_repos = official_repos_result.fetchone().count

                # Get papers with official repositories
                papers_with_official_repos_result = session.execute(
                    text("""
                        SELECT COUNT(DISTINCT p.id) as count
                        FROM papers p
                        INNER JOIN repositories r ON p.id = r.paper_id
                        WHERE r.is_official = true
                    """)
                )
                papers_with_official_repos = (
                    papers_with_official_repos_result.fetchone().count
                )

                # Get repository distribution by stars (if available)
                repo_stars_distribution = session.execute(
                    text("""
                        SELECT
                            star_range,
                            COUNT(*) as count
                        FROM (
                            SELECT
                                CASE
                                    WHEN num_stars = 0 THEN '0 stars'
                                    WHEN num_stars BETWEEN 1 AND 10 THEN '1-10 stars'
                                    WHEN num_stars BETWEEN 11 AND 50 THEN '11-50 stars'
                                    WHEN num_stars BETWEEN 51 AND 100 THEN '51-100 stars'
                                    WHEN num_stars BETWEEN 101 AND 500 THEN '101-500 stars'
                                    WHEN num_stars BETWEEN 501 AND 1000 THEN '501-1000 stars'
                                    WHEN num_stars > 1000 THEN '1000+ stars'
                                    ELSE 'Unknown'
                                END as star_range,
                                CASE
                                    WHEN num_stars = 0 THEN 1
                                    WHEN num_stars BETWEEN 1 AND 10 THEN 2
                                    WHEN num_stars BETWEEN 11 AND 50 THEN 3
                                    WHEN num_stars BETWEEN 51 AND 100 THEN 4
                                    WHEN num_stars BETWEEN 101 AND 500 THEN 5
                                    WHEN num_stars BETWEEN 501 AND 1000 THEN 6
                                    WHEN num_stars > 1000 THEN 7
                                    ELSE 8
                                END as sort_order
                            FROM repositories
                        ) as categorized
                        GROUP BY star_range, sort_order
                        ORDER BY sort_order
                    """)
                ).fetchall()

                # Calculate percentages
                coverage_percentage = (
                    (papers_with_repos / total_papers * 100) if total_papers > 0 else 0
                )
                official_coverage_percentage = (
                    (papers_with_official_repos / total_papers * 100)
                    if total_papers > 0
                    else 0
                )
                multiple_repos_percentage = (
                    (papers_multiple_repos / papers_with_repos * 100)
                    if papers_with_repos > 0
                    else 0
                )

                # Compile results
                results = {
                    "total_papers": total_papers,
                    "papers_with_repos": papers_with_repos,
                    "papers_without_repos": total_papers - papers_with_repos,
                    "coverage_percentage": round(coverage_percentage, 2),
                    "total_repositories": total_repos,
                    "avg_repos_per_paper": round(total_repos / papers_with_repos, 2)
                    if papers_with_repos > 0
                    else 0,
                    "papers_with_multiple_repos": papers_multiple_repos,
                    "multiple_repos_percentage": round(multiple_repos_percentage, 2),
                    "official_repositories": official_repos,
                    "papers_with_official_repos": papers_with_official_repos,
                    "official_coverage_percentage": round(
                        official_coverage_percentage, 2
                    ),
                    "star_distribution": {
                        row.star_range: row.count for row in repo_stars_distribution
                    },
                }

                logger.info("Repository coverage analysis completed successfully")
                return results

            except Exception as e:
                logger.error(f"Error during analysis: {e}")
                raise

    def print_results(self, results: Dict[str, Any]):
        """Print formatted analysis results."""
        print("\n" + "=" * 60)
        print("📊 PAPERSWITHCODE REPOSITORY COVERAGE ANALYSIS")
        print("=" * 60)

        print("\n📄 PAPERS OVERVIEW:")
        print(f"   Total papers in database: {results['total_papers']:,}")
        print(f"   Papers with repositories: {results['papers_with_repos']:,}")
        print(f"   Papers without repositories: {results['papers_without_repos']:,}")

        print("\n🎯 COVERAGE STATISTICS:")
        print(f"   Repository coverage: {results['coverage_percentage']:.2f}%")
        print(
            f"   Official repository coverage: {results['official_coverage_percentage']:.2f}%"
        )

        print("\n📁 REPOSITORY DETAILS:")
        print(f"   Total repository entries: {results['total_repositories']:,}")
        print(f"   Official repositories: {results['official_repositories']:,}")
        print(f"   Average repos per paper: {results['avg_repos_per_paper']:.2f}")
        print(
            f"   Papers with multiple repos: {results['papers_with_multiple_repos']:,} ({results['multiple_repos_percentage']:.2f}%)"
        )

        if results["star_distribution"]:
            print("\n⭐ REPOSITORY POPULARITY (by GitHub stars):")
            for star_range, count in results["star_distribution"].items():
                percentage = (
                    (count / results["total_repositories"] * 100)
                    if results["total_repositories"] > 0
                    else 0
                )
                print(f"   {star_range}: {count:,} repos ({percentage:.1f}%)")

        print("\n💡 KEY INSIGHTS:")
        if results["coverage_percentage"] < 10:
            print(
                f"   • Low repository coverage - only {results['coverage_percentage']:.1f}% of papers have linked repos"
            )
        elif results["coverage_percentage"] < 25:
            print(
                f"   • Moderate repository coverage - {results['coverage_percentage']:.1f}% of papers have linked repos"
            )
        elif results["coverage_percentage"] < 50:
            print(
                f"   • Good repository coverage - {results['coverage_percentage']:.1f}% of papers have linked repos"
            )
        else:
            print(
                f"   • Excellent repository coverage - {results['coverage_percentage']:.1f}% of papers have linked repos"
            )

        if results["official_coverage_percentage"] > 0:
            print(
                f"   • {results['official_coverage_percentage']:.1f}% of papers have official repositories"
            )

        if results["multiple_repos_percentage"] > 10:
            print(
                f"   • {results['multiple_repos_percentage']:.1f}% of papers with repos have multiple implementations"
            )

        print("=" * 60)


def main():
    """Main function to run the repository coverage analysis."""
    try:
        analyzer = RepositoryCoverageAnalyzer()
        results = analyzer.analyze_coverage()
        analyzer.print_results(results)

        # Return results for potential programmatic use
        return results

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
