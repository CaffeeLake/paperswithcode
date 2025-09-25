#!/usr/bin/env python3
"""
Batch PDF Downloader for 80GB Disk Constraint

Downloads ArXiv PDFs in manageable batches, optimized for limited disk space.
Focuses on most important papers first.
"""

import csv
import time
import requests
from pathlib import Path
import logging
from typing import List, Set
import random
import json
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("batch_download.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class SmartBatchDownloader:
    """Downloads PDFs in batches optimized for disk space constraints."""

    def __init__(
        self, output_dir: str = "arxiv_pdfs/downloaded", batch_size_gb: float = 15.0
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Disk space management
        self.batch_size_gb = batch_size_gb
        self.current_batch_size = 0
        self.batch_number = 1

        # Rate limiting (conservative based on test results)
        self.min_delay = 30  # 30 seconds minimum
        self.max_delay = 60  # 60 seconds maximum

        # Session with rotating headers
        self.session = requests.Session()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        # Statistics
        self.stats = {
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "html_responses": 0,
            "current_batch_mb": 0,
        }

        # Progress tracking
        self.progress_file = "download_progress.json"
        self.completed_papers = self.load_progress()

    def load_progress(self) -> Set[str]:
        """Load previously downloaded papers."""
        if Path(self.progress_file).exists():
            try:
                with open(self.progress_file, "r") as f:
                    data = json.load(f)
                    return set(data.get("completed", []))
            except:  # noqa: E722
                pass
        return set()

    def save_progress(self):
        """Save download progress."""
        try:
            data = {
                "completed": list(self.completed_papers),
                "stats": self.stats,
                "batch_number": self.batch_number,
            }
            with open(self.progress_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save progress: {e}")

    def prioritize_papers(self, arxiv_ids: List[str]) -> List[str]:
        """Prioritize papers by recency and likely importance."""

        # Separate by year (recent papers first)
        by_year = defaultdict(list)

        for arxiv_id in arxiv_ids:
            if arxiv_id in self.completed_papers:
                continue

            # Extract year from ArXiv ID
            try:
                if "." in arxiv_id:
                    year_month = arxiv_id.split(".")[0]
                    if len(year_month) >= 2:
                        if year_month.startswith("9"):  # 91xx = 19xx
                            year = int(f"19{year_month[:2]}")
                        else:  # 23xx = 20xx
                            year = int(f"20{year_month[:2]}")
                        by_year[year].append(arxiv_id)
            except:  # noqa: E722
                by_year[2020].append(arxiv_id)  # Default year

        # Prioritize: 2025 first, then 2024, 2023, etc.
        priority_order = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016]
        priority_order.extend(range(2015, 1990, -1))  # Add remaining years

        prioritized = []
        for year in priority_order:
            if year in by_year:
                # Shuffle within year to avoid patterns
                papers = by_year[year]
                random.shuffle(papers)
                prioritized.extend(papers)

        # Add any remaining papers
        for year, papers in by_year.items():
            if year not in priority_order:
                prioritized.extend(papers)

        # Log year distribution
        logger.info("📊 Paper distribution by year:")
        for year in priority_order[:10]:  # Show top 10 years
            if year in by_year:
                count = len(by_year[year])
                logger.info(f"   {year}: {count:,} papers")

        logger.info(
            f"📊 Prioritized {len(prioritized)} papers (skipped {len(self.completed_papers)} already downloaded)"
        )
        return prioritized

    def update_headers(self):
        """Update session headers with random user agent."""
        self.session.headers.update(
            {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "application/pdf,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )

    def download_pdf(self, arxiv_id: str) -> bool:
        """Download a single PDF."""
        pdf_path = self.output_dir / f"{arxiv_id}.pdf"

        # Skip if already exists
        if pdf_path.exists():
            self.stats["skipped"] += 1
            return True

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        try:
            # Update headers occasionally
            if random.random() < 0.1:
                self.update_headers()

            logger.info(f"📥 Downloading {arxiv_id}")

            response = self.session.get(pdf_url, timeout=45)
            response.raise_for_status()

            content = response.content

            # Check if we got a PDF
            if not content.startswith(b"%PDF-"):
                # Check if it's HTML (soft rate limiting)
                if b"<html" in content[:500].lower():
                    logger.warning(f"⚠️  Got HTML for {arxiv_id} - soft rate limited")
                    self.stats["html_responses"] += 1
                    return False
                else:
                    logger.error(f"❌ Invalid content for {arxiv_id}")
                    self.stats["failed"] += 1
                    return False

            # Save PDF
            with open(pdf_path, "wb") as f:
                f.write(content)

            file_size_mb = len(content) / (1024 * 1024)
            self.stats["current_batch_mb"] += file_size_mb
            self.current_batch_size += file_size_mb / 1024  # Convert to GB

            logger.info(f"✅ Downloaded {arxiv_id} ({file_size_mb:.1f} MB)")
            self.stats["downloaded"] += 1
            self.completed_papers.add(arxiv_id)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to download {arxiv_id}: {e}")
            self.stats["failed"] += 1
            return False

    def check_disk_space(self) -> bool:
        """Check if we should start a new batch."""
        return self.current_batch_size >= self.batch_size_gb

    def start_new_batch(self):
        """Start a new batch (user needs to free up space)."""
        logger.info("=" * 60)
        logger.info(f"📦 BATCH {self.batch_number} COMPLETE")
        logger.info(f"💾 Downloaded: {self.stats['current_batch_mb']:.1f} MB")
        logger.info(
            f"📊 Success rate: {self.stats['downloaded']}/{self.stats['downloaded'] + self.stats['failed']}"
        )
        logger.info("=" * 60)
        logger.info("🚨 DISK SPACE MANAGEMENT NEEDED")
        logger.info("Please:")
        logger.info("1. 📁 Process/move downloaded PDFs to free up space")
        logger.info("2. 🗑️  Delete processed files or move to external storage")
        logger.info("3. ▶️  Run this script again to continue with next batch")
        logger.info("=" * 60)

        # Reset batch counters
        self.batch_number += 1
        self.current_batch_size = 0
        self.stats["current_batch_mb"] = 0

        # Save progress
        self.save_progress()

    def download_batch(self, arxiv_ids: List[str], max_papers: int = None):
        """Download a batch of papers."""

        # Prioritize papers
        prioritized_papers = self.prioritize_papers(arxiv_ids)

        if max_papers:
            prioritized_papers = prioritized_papers[:max_papers]

        logger.info(f"🚀 Starting batch {self.batch_number}")
        logger.info(f"📊 Target papers: {len(prioritized_papers)}")
        logger.info(f"💾 Batch size limit: {self.batch_size_gb:.1f} GB")
        logger.info(f"⏱️  Rate limiting: {self.min_delay}-{self.max_delay} seconds")

        for i, arxiv_id in enumerate(prioritized_papers, 1):
            # Check disk space
            if self.check_disk_space():
                logger.info(
                    f"💾 Batch size limit reached ({self.batch_size_gb:.1f} GB)"
                )
                self.start_new_batch()
                break

            logger.info(
                f"📈 Progress: {i}/{len(prioritized_papers)} ({i / len(prioritized_papers) * 100:.1f}%)"
            )

            # Download paper
            success = self.download_pdf(arxiv_id)

            # Rate limiting
            if i < len(prioritized_papers):
                delay = random.uniform(self.min_delay, self.max_delay)

                # Extra delay if we got HTML response
                if not success and self.stats["html_responses"] > 0:
                    delay += 30
                    logger.info("⏳ Extra delay due to rate limiting...")

                logger.info(f"⏱️  Waiting {delay:.1f} seconds...")
                time.sleep(delay)

            # Save progress periodically
            if i % 10 == 0:
                self.save_progress()

        # Final save
        self.save_progress()

        # Final stats
        logger.info("=" * 60)
        logger.info("📊 DOWNLOAD SESSION COMPLETE")
        logger.info(f"✅ Downloaded: {self.stats['downloaded']}")
        logger.info(f"⏭️  Skipped: {self.stats['skipped']}")
        logger.info(f"❌ Failed: {self.stats['failed']}")
        logger.info(f"⚠️  HTML responses: {self.stats['html_responses']}")
        logger.info(f"💾 Current batch size: {self.stats['current_batch_mb']:.1f} MB")
        logger.info("=" * 60)


def load_arxiv_ids(csv_file: str) -> List[str]:
    """Load ArXiv IDs from CSV file."""
    arxiv_ids = []
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            if row and row[0].strip():
                arxiv_ids.append(row[0].strip())
    return arxiv_ids


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart Batch PDF Downloader for 80GB Constraint"
    )
    parser.add_argument("--csv", default="data/arxiv_papers_hf.csv")
    parser.add_argument("--output-dir", default="arxiv_pdfs/downloaded")
    parser.add_argument(
        "--batch-size-gb",
        type=float,
        default=15.0,
        help="Batch size in GB (default: 15GB)",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=None,
        help="Maximum papers to download in this session",
    )

    args = parser.parse_args()

    # Load papers
    arxiv_ids = load_arxiv_ids(args.csv)
    logger.info(f"📚 Loaded {len(arxiv_ids)} ArXiv IDs")

    # Start downloader
    downloader = SmartBatchDownloader(args.output_dir, args.batch_size_gb)
    downloader.download_batch(arxiv_ids, args.max_papers)


if __name__ == "__main__":
    main()
