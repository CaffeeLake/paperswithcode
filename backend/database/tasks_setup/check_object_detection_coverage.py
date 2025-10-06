#!/usr/bin/env python3
"""
Check how many object detection papers from data/object_detection_papers.json
are present in the PostgreSQL database.

Matches papers based on arxiv_id.
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Set, Dict, Any
import os
from pathlib import Path


def load_object_detection_papers(json_path: str) -> List[Dict[str, Any]]:
    """Load papers from the JSON file."""
    print(f"Loading papers from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        papers = json.load(f)
    print(f"Loaded {len(papers):,} papers from JSON file")
    return papers


def extract_arxiv_ids(papers: List[Dict[str, Any]]) -> Set[str]:
    """Extract unique arxiv_ids from the papers list."""
    arxiv_ids = set()
    papers_without_arxiv = 0

    for paper in papers:
        arxiv_id = paper.get("arxiv_id")
        if arxiv_id:
            # Clean the arxiv_id - remove version suffix if present
            # e.g., "1805.10616v2" -> "1805.10616"
            base_arxiv_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            arxiv_ids.add(base_arxiv_id)
        else:
            papers_without_arxiv += 1

    print(f"Extracted {len(arxiv_ids):,} unique arxiv_ids")
    if papers_without_arxiv > 0:
        print(f"Warning: {papers_without_arxiv:,} papers have no arxiv_id")

    return arxiv_ids


def check_database_coverage(arxiv_ids: Set[str]) -> Dict[str, Any]:
    """Check how many of the arxiv_ids exist in the database."""
    print("\nConnecting to PostgreSQL database...")

    conn = None
    try:
        # Connect to database
        conn = psycopg2.connect(
            database=os.getenv("DB_NAME", "paperswithcode_hf"),
            user=os.getenv("DB_USER", "paperswithcode_user"),
            password=os.getenv("DB_PASSWORD", "paperswithcode123"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Convert set to list for SQL query
            arxiv_id_list = list(arxiv_ids)

            # Check how many papers exist in database
            print(f"Checking {len(arxiv_id_list):,} arxiv_ids in database...")

            # Query for matching papers (checking latest versions)
            cur.execute(
                """
                SELECT
                    arxiv_id,
                    version,
                    is_latest_version,
                    title,
                    date_published
                FROM papers
                WHERE arxiv_id = ANY(%s)
                ORDER BY arxiv_id, version DESC
            """,
                (arxiv_id_list,),
            )

            matching_papers = cur.fetchall()

            # Get unique arxiv_ids found
            found_arxiv_ids = set(paper["arxiv_id"] for paper in matching_papers)

            # Get latest version papers only
            latest_papers = [p for p in matching_papers if p["is_latest_version"]]

            # Papers not found in database
            not_found = arxiv_ids - found_arxiv_ids

            # Get some sample papers that were found and not found
            sample_found = list(found_arxiv_ids)[:5]
            sample_not_found = list(not_found)[:5]

            # Get statistics on versions
            version_counts: Dict[str, int] = {}
            for paper in matching_papers:
                arxiv_id = paper["arxiv_id"]
                version_counts[arxiv_id] = version_counts.get(arxiv_id, 0) + 1

            # Papers with multiple versions
            multi_version_papers = {k: v for k, v in version_counts.items() if v > 1}

            results = {
                "total_json_papers": len(arxiv_ids),
                "total_found": len(found_arxiv_ids),
                "total_not_found": len(not_found),
                "total_matching_rows": len(matching_papers),
                "latest_version_papers": len(latest_papers),
                "coverage_percentage": (len(found_arxiv_ids) / len(arxiv_ids) * 100)
                if arxiv_ids
                else 0,
                "papers_with_multiple_versions": len(multi_version_papers),
                "sample_found": sample_found,
                "sample_not_found": sample_not_found,
                "multi_version_examples": dict(list(multi_version_papers.items())[:5]),
            }

            return results

    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise
    finally:
        if conn:
            conn.close()


def print_results(results: Dict[str, Any]) -> None:
    """Print the coverage statistics in a readable format."""
    print("\n" + "=" * 80)
    print("OBJECT DETECTION PAPERS - DATABASE COVERAGE REPORT")
    print("=" * 80)

    print("\n📊 SUMMARY:")
    print(f"  Total papers in JSON:           {results['total_json_papers']:>10,}")
    print(f"  Papers found in database:       {results['total_found']:>10,}")
    print(f"  Papers NOT found in database:   {results['total_not_found']:>10,}")
    print(f"  Coverage:                       {results['coverage_percentage']:>10.2f}%")

    print("\n📄 VERSION INFORMATION:")
    print(f"  Total matching database rows:   {results['total_matching_rows']:>10,}")
    print(f"  Latest version papers:          {results['latest_version_papers']:>10,}")
    print(
        f"  Papers with multiple versions:  {results['papers_with_multiple_versions']:>10,}"
    )

    if results["sample_found"]:
        print("\n✅ Sample arxiv_ids FOUND in database:")
        for arxiv_id in results["sample_found"]:
            print(f"     - {arxiv_id}")

    if results["sample_not_found"]:
        print("\n❌ Sample arxiv_ids NOT FOUND in database:")
        for arxiv_id in results["sample_not_found"]:
            print(f"     - {arxiv_id}")

    if results["multi_version_examples"]:
        print("\n🔄 Sample papers with multiple versions:")
        for arxiv_id, count in results["multi_version_examples"].items():
            print(f"     - {arxiv_id}: {count} versions")

    print("\n" + "=" * 80)


def main():
    """Main function to run the coverage check."""
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    json_path = project_root / "data" / "object_detection_papers.json"

    # Check if file exists
    if not json_path.exists():
        print(f"Error: File not found at {json_path}")
        return

    # Load papers from JSON
    papers = load_object_detection_papers(str(json_path))

    # Extract arxiv_ids
    arxiv_ids = extract_arxiv_ids(papers)

    # Check database coverage
    results = check_database_coverage(arxiv_ids)

    # Print results
    print_results(results)

    # Save detailed results to file
    output_path = project_root / "data" / "object_detection_coverage_report.json"
    print(f"\n💾 Saving detailed report to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("✅ Report saved successfully!")


if __name__ == "__main__":
    main()
