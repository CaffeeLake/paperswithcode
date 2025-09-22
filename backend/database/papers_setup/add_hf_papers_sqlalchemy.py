#!/usr/bin/env python3
"""
Modern HF Dataset Paper Importer using SQLAlchemy-based PaperService.

This script imports papers from the Hugging Face community science dataset
that are missing from our database. It uses the proper SQLAlchemy-based
PaperService instead of the legacy psycopg2 approach.

Usage:
    PYTHONPATH=/root/python_projects/paperswithcode uv run --env-file backend/keys.env python backend/database/setup/add_hf_papers_sqlalchemy.py [--limit N]
"""

import sys
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
import re
import argparse
from datetime import datetime
from datasets import load_dataset
from typing import List, Set, Dict, Optional, Any

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
        print(f"Error loading dataset: {e}")
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


def fetch_arxiv_paper_details(
    arxiv_id: str, retry_count: int = 3
) -> Optional[Dict[str, Any]]:
    """Fetch paper details from ArXiv API by ArXiv ID with retry logic."""

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

            # Extract categories
            categories = [cat.get("term") for cat in entry.findall("atom:category", ns)]
            primary_category = categories[0] if categories else None

            return {
                "arxiv_id": extracted_arxiv_id,
                "title": title,
                "abstract": summary,
                "version": version,
                "date_published": pub_date,
                "is_latest_version": True,
                "proceeding": None,
                "conference": None,
                "conference_url_abs": None,
                "conference_url_pdf": None,
                "primary_category": primary_category,
                "all_categories": categories,
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


def add_missing_papers_batch(
    missing_ids: Set[str],
    hf_df: pd.DataFrame,
    paper_service: PaperService,
    batch_size: int = 50,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """Add missing papers to the database in batches."""

    results = {"attempted": 0, "successful": 0, "failed": 0, "skipped": 0}

    # Create a mapping of arxiv_id to HF dataset info for reference
    hf_info = hf_df.set_index("arxiv_id").to_dict("index")

    missing_ids_list = list(missing_ids)

    # Apply limit if specified
    if limit and limit < len(missing_ids_list):
        missing_ids_list = missing_ids_list[:limit]
        print(f"Limiting processing to first {limit} papers")

    total_papers = len(missing_ids_list)

    print(
        f"Starting to process {total_papers} missing papers in batches of {batch_size}..."
    )

    # Process in batches
    for batch_start in range(0, total_papers, batch_size):
        batch_end = min(batch_start + batch_size, total_papers)
        batch_ids = missing_ids_list[batch_start:batch_end]

        print(
            f"\n=== Processing batch {batch_start // batch_size + 1}/{(total_papers + batch_size - 1) // batch_size} ==="
        )
        print(f"Papers {batch_start + 1}-{batch_end} of {total_papers}")

        # Process this batch
        batch_results = process_batch(batch_ids, hf_info, paper_service, batch_start)

        # Update overall results
        for key in results:
            results[key] += batch_results[key]

        # Progress update
        print(
            f"Batch complete. Overall progress: {results['successful']}/{results['attempted']} successful"
        )

        # Longer pause between batches to be respectful to ArXiv API
        if batch_end < total_papers:
            print("Pausing between batches...")
            time.sleep(5)

    return results


def process_batch(
    batch_ids: List[str], hf_info: Dict, paper_service: PaperService, batch_start: int
) -> Dict[str, int]:
    """Process a single batch of papers."""

    batch_results = {"attempted": 0, "successful": 0, "failed": 0, "skipped": 0}

    try:
        for i, arxiv_id in enumerate(batch_ids, 1):
            batch_results["attempted"] += 1

            print(f"  Processing {i}/{len(batch_ids)}: {arxiv_id}")

            # Get HF dataset info for this paper (if available)
            hf_paper_info = hf_info.get(arxiv_id, {})

            # Try to fetch from ArXiv API
            paper_data = fetch_arxiv_paper_details(arxiv_id)

            if paper_data:
                # Use ArXiv data as primary source
                print(f"    Found: {paper_data['title'][:50]}...")

                # Optionally enrich with HF data if available
                if (
                    "conference_name" in hf_paper_info
                    and hf_paper_info["conference_name"]
                ):
                    paper_data["conference"] = hf_paper_info["conference_name"]

            elif hf_paper_info:
                # Fallback to HF data if ArXiv fetch failed
                print(
                    f"    Using HF data: {hf_paper_info.get('title', 'No title')[:50]}..."
                )

                # Convert HF data to our format
                paper_data = {
                    "arxiv_id": arxiv_id,
                    "version": "v1",  # Default version since HF doesn't track versions
                    "title": hf_paper_info.get("title", f"Paper {arxiv_id}"),
                    "abstract": None,  # HF dataset might not have abstracts
                    "date_published": datetime.strptime(
                        hf_paper_info["date"], "%Y-%m-%d"
                    ).date()
                    if "date" in hf_paper_info
                    else None,
                    "is_latest_version": True,
                    "proceeding": None,
                    "conference": hf_paper_info.get("conference_name"),
                    "conference_url_abs": None,
                    "conference_url_pdf": None,
                }
            else:
                print(f"    No data found for {arxiv_id}")
                batch_results["failed"] += 1
                continue

            # Insert into database using PaperService
            paper_id = paper_service.add_paper(paper_data)
            if paper_id:
                batch_results["successful"] += 1
            else:
                batch_results["skipped"] += 1
                print(f"    Skipped (likely duplicate): {arxiv_id}")

            # Rate limiting within batch
            if i % 10 == 0:
                time.sleep(1)

        return batch_results

    except Exception as e:
        print(f"Error processing batch: {e}")
        return batch_results


def main():
    """Main function to add missing papers from HF dataset."""

    parser = argparse.ArgumentParser(
        description="Add missing papers from HF dataset to database (SQLAlchemy version)"
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of papers to process (for testing)"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check coverage, don't add papers",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Batch size for processing"
    )

    args = parser.parse_args()

    print("🔬 HF Dataset Paper Importer (SQLAlchemy Version)")
    print("=" * 50)

    # Load HF dataset
    df = load_hf_dataset()
    if df is None:
        print("❌ Failed to load dataset")
        return 1

    # Get database session and create paper service
    try:
        db_session = next(get_database_session())
        paper_service = PaperService(db_session)

        # Get missing ArXiv IDs
        missing_ids = get_missing_arxiv_ids(df, paper_service)
        if not missing_ids:
            print("✅ No missing papers found! Database is up to date.")
            return 0

        print(f"\n📊 Found {len(missing_ids)} missing papers")

        if args.check_only:
            print("✅ Check complete (--check-only specified)")
            return 0

        if args.limit:
            print(f"🔧 Processing limited to {args.limit} papers")

        # Add missing papers in batches
        start_time = datetime.now()
        results = add_missing_papers_batch(
            missing_ids, df, paper_service, batch_size=args.batch_size, limit=args.limit
        )
        end_time = datetime.now()

        if results:
            print("\n=== FINAL RESULTS ===")
            print(f"Processing time: {end_time - start_time}")
            print(f"Papers attempted: {results['attempted']}")
            print(f"Successfully added: {results['successful']}")
            print(f"Failed to fetch: {results['failed']}")
            print(f"Skipped (duplicates): {results['skipped']}")

            success_rate = (
                (results["successful"] / results["attempted"]) * 100
                if results["attempted"] > 0
                else 0
            )
            print(f"Success rate: {success_rate:.1f}%")

            # Calculate new coverage estimate
            if results["successful"] > 0:
                total_hf_papers = len(df)
                # Estimate current papers in DB (original found + newly added)
                estimated_in_db = (total_hf_papers - len(missing_ids)) + results[
                    "successful"
                ]
                estimated_coverage = (estimated_in_db / total_hf_papers) * 100
                print(f"Estimated new coverage: {estimated_coverage:.1f}%")

            return 0 if results["successful"] > 0 else 1
        else:
            print("❌ Processing failed")
            return 1

    except Exception as e:
        print(f"❌ Database error: {e}")
        return 1
    finally:
        if "db_session" in locals():
            db_session.close()


if __name__ == "__main__":
    sys.exit(main())
