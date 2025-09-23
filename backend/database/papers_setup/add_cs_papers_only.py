#!/usr/bin/env python3
"""
CS-Only Paper Importer - Import only Computer Science papers from Hugging Face dataset.

This script imports papers from the Hugging Face community science dataset
but filters to only include Computer Science papers (cs.* categories).

This helps focus the database on relevant papers and reduces storage/processing overhead.

Usage:
    uv run backend/database/papers_setup/add_cs_papers_only.py --limit 1000
"""

import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
import re
import argparse
from datetime import datetime
from datasets import load_dataset
from typing import Set, Dict, Optional, Any

from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService
from backend.models.database import Paper as DBPaper


def load_hf_dataset() -> pd.DataFrame:
    """Load the Hugging Face community science dataset."""
    try:
        print("Loading Hugging Face dataset: huggingface/community-science-merged")
        dataset = load_dataset("huggingface/community-science-merged")

        # Convert to pandas DataFrame
        if "train" in dataset:
            df = dataset["train"].to_pandas()
        else:
            split_name = list(dataset.keys())[0]
            df = dataset[split_name].to_pandas()

        print(f"Dataset loaded successfully with {len(df)} rows")
        print(f"Available columns: {list(df.columns)}")

        # Show sample data to understand structure
        print("\nSample data:")
        print(df[["arxiv_id", "title", "date"]].head())

        return df

    except Exception as e:
        print(f"Error loading HF dataset: {e}")
        return None


def get_missing_arxiv_ids(df: pd.DataFrame, paper_service: PaperService) -> Set[str]:
    """Get ArXiv IDs that are missing from our database."""

    try:
        # Get all ArXiv IDs from HF dataset
        hf_arxiv_ids = set(df["arxiv_id"].dropna().astype(str))
        print(f"Found {len(hf_arxiv_ids)} ArXiv IDs in HF dataset")

        # Check which ones are missing from our database
        found_count = 0
        missing_ids = set()

        for arxiv_id in hf_arxiv_ids:
            # Check if paper exists in database
            existing = (
                paper_service.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id)
                .first()
            )

            if existing:
                found_count += 1
            else:
                missing_ids.add(arxiv_id)

        print(f"Found {found_count} ArXiv IDs already in database")
        print(f"Missing {len(missing_ids)} ArXiv IDs from database")

        # Calculate current coverage
        coverage = (found_count / len(hf_arxiv_ids)) * 100
        print(f"Current coverage: {coverage:.1f}%")

        return missing_ids

    except Exception as e:
        print(f"Error checking database: {e}")
        return set()


def fetch_arxiv_paper_details_cs_only(
    arxiv_id: str, retry_count: int = 3
) -> Optional[Dict[str, Any]]:
    """Fetch paper details from ArXiv API, returning only CS papers."""

    for attempt in range(retry_count):
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }

            entries = root.findall("atom:entry", ns)
            if not entries:
                if attempt < retry_count - 1:
                    print(f"    No entry found for {arxiv_id}, retrying...")
                    time.sleep(2)
                    continue
                else:
                    print(f"    No entry found for ArXiv ID: {arxiv_id}")
                    return None

            entry = entries[0]  # Take the first (should be only) entry

            # Extract categories FIRST to filter early
            categories = [cat.get("term") for cat in entry.findall("atom:category", ns)]
            primary_category = categories[0] if categories else None

            # FILTER: Only process Computer Science papers
            if not primary_category or not primary_category.startswith("cs."):
                print(f"    ❌ Skipping non-CS paper: {arxiv_id} ({primary_category})")
                return None

            print(f"    ✅ CS paper found: {arxiv_id} ({primary_category})")

            # Extract ArXiv ID and version from the full ID
            full_id = entry.find("atom:id", ns).text.split("/")[-1]
            arxiv_match = re.match(r"(\d+\.\d+)(v\d+)?", full_id)
            if not arxiv_match:
                print(f"    Could not parse ArXiv ID: {full_id}")
                return None

            extracted_arxiv_id = arxiv_match.group(1)
            version = arxiv_match.group(2) or "v1"

            # Extract paper details
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")

            # Extract publication date
            published = entry.find("atom:published", ns).text
            pub_date = datetime.fromisoformat(published.replace("Z", "+00:00")).date()

            # Extract authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns).text
                authors.append(name)

            return {
                "arxiv_id": extracted_arxiv_id,
                "version": version,
                "title": title,
                "abstract": summary,
                "date_published": pub_date,
                "is_latest_version": True,
                "proceeding": None,
                "conference": None,
                "conference_url_abs": None,
                "conference_url_pdf": None,
                "primary_category": primary_category,
                "all_categories": categories,
                "authors": authors,
            }

        except requests.RequestException as e:
            if attempt < retry_count - 1:
                print(
                    f"    Request error for {arxiv_id} (attempt {attempt + 1}), retrying: {e}"
                )
                time.sleep(5)  # Longer delay on network errors
                continue
            else:
                print(f"    Error fetching ArXiv paper {arxiv_id}: {e}")
                return None
        except ET.ParseError as e:
            print(f"    Error parsing XML for ArXiv paper {arxiv_id}: {e}")
            return None
        except Exception as e:
            print(f"    Unexpected error for ArXiv paper {arxiv_id}: {e}")
            return None

    return None


def add_missing_papers_batch_cs_only(
    missing_ids: Set[str],
    hf_df: pd.DataFrame,
    paper_service: PaperService,
    batch_size: int = 50,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """Add missing CS papers to database in batches."""

    stats = {
        "total_checked": 0,
        "cs_papers_found": 0,
        "non_cs_papers_skipped": 0,
        "papers_added": 0,
        "api_errors": 0,
        "database_errors": 0,
    }

    # Convert to list and limit if specified
    missing_list = list(missing_ids)
    if limit:
        missing_list = missing_list[:limit]

    print(f"\n🔍 Processing {len(missing_list)} missing ArXiv IDs (CS-only filter)")

    # Process in batches
    for i in range(0, len(missing_list), batch_size):
        batch = missing_list[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(missing_list) + batch_size - 1) // batch_size

        print(
            f"\n📦 Processing batch {batch_num}/{total_batches} ({len(batch)} papers)"
        )

        batch_papers = []
        for arxiv_id in batch:
            stats["total_checked"] += 1

            print(f"  Checking {arxiv_id}...")

            # Fetch full details from ArXiv API (with CS filtering)
            paper_details = fetch_arxiv_paper_details_cs_only(arxiv_id)

            if paper_details is None:
                if "No entry found" not in str(paper_details):
                    stats["api_errors"] += 1
                else:
                    stats["non_cs_papers_skipped"] += 1
                continue

            stats["cs_papers_found"] += 1

            # Prepare paper data for database
            paper_data = {
                "title": paper_details["title"],
                "abstract": paper_details["abstract"],
                "arxiv_id": paper_details["arxiv_id"],
                "version": paper_details["version"],
                "is_latest_version": paper_details["is_latest_version"],
                "date_published": paper_details["date_published"],
                "proceeding": paper_details.get("proceeding"),
                "conference": paper_details.get("conference"),
                "conference_url_abs": paper_details.get("conference_url_abs"),
                "conference_url_pdf": paper_details.get("conference_url_pdf"),
                "citation_count": 0,
                "semantic_scholar_id": None,
                "primary_category": paper_details["primary_category"],
                "all_categories": paper_details["all_categories"],
            }

            batch_papers.append(paper_data)

            # Rate limiting
            time.sleep(0.2)

        # Add batch to database
        if batch_papers:
            try:
                for paper_data in batch_papers:
                    paper_service.create_paper(paper_data)
                    stats["papers_added"] += 1
                    print(
                        f"    ✅ Added: {paper_data['arxiv_id']} ({paper_data['primary_category']})"
                    )

                print(
                    f"  📊 Batch {batch_num} complete: {len(batch_papers)} CS papers added"
                )

            except Exception as e:
                print(f"  ❌ Database error in batch {batch_num}: {e}")
                stats["database_errors"] += len(batch_papers)

        # Brief pause between batches
        time.sleep(1)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import CS-only papers from Hugging Face dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of papers to process", default=None
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of papers to process in each batch",
        default=50,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't add papers, just show what would be done",
    )

    args = parser.parse_args()

    # Load HF dataset
    hf_df = load_hf_dataset()
    if hf_df is None:
        print("❌ Failed to load HF dataset")
        return

    # Get database session and create PaperService
    db_session_gen = get_database_session()
    db_session = next(db_session_gen)

    try:
        paper_service = PaperService(db_session)

        # Test connection
        try:
            stats = paper_service.get_paper_stats()
            print(
                f"✅ Database connection successful! Current papers: {stats['total_papers']:,}"
            )
        except Exception as e:
            raise Exception(f"Database connection failed: {e}")

        # Get missing ArXiv IDs
        missing_ids = get_missing_arxiv_ids(hf_df, paper_service)

        if not missing_ids:
            print("✅ All papers from HF dataset are already in database!")
            return

        if args.dry_run:
            print(f"🔍 DRY RUN MODE - Would process {len(missing_ids)} missing papers")
            # Show first few examples
            for i, arxiv_id in enumerate(list(missing_ids)[:5]):
                print(f"  Would check: {arxiv_id}")
            return

        # Add missing papers (CS-only)
        import_stats = add_missing_papers_batch_cs_only(
            missing_ids, hf_df, paper_service, args.batch_size, args.limit
        )

        # Print final statistics
        print("\n" + "=" * 60)
        print("📊 CS-ONLY IMPORT COMPLETE")
        print("=" * 60)
        print(f"📄 Total Papers Checked: {import_stats['total_checked']}")
        print(f"✅ CS Papers Found: {import_stats['cs_papers_found']}")
        print(f"❌ Non-CS Papers Skipped: {import_stats['non_cs_papers_skipped']}")
        print(f"💾 Papers Added to Database: {import_stats['papers_added']}")
        print(f"⚠️  API Errors: {import_stats['api_errors']}")
        print(f"⚠️  Database Errors: {import_stats['database_errors']}")

        if import_stats["total_checked"] > 0:
            cs_percentage = (
                import_stats["cs_papers_found"] / import_stats["total_checked"] * 100
            )
            print(f"📈 CS Paper Rate: {cs_percentage:.1f}%")

        # Show updated database stats
        final_stats = paper_service.get_paper_stats()
        print(f"📊 Final Database: {final_stats['total_papers']:,} papers")

    except Exception as e:
        print(f"❌ Error during import: {e}")
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
