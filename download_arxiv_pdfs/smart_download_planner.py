#!/usr/bin/env python3
"""
Smart ArXiv Download Planner

Creates an optimized download plan that minimizes cost while maximizing paper coverage.
"""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
import logging
from typing import Set, List, Dict
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_target_arxiv_ids(csv_file: str) -> Set[str]:
    """Load ArXiv IDs we want to download."""
    target_ids = set()

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header

        for row in reader:
            if row and row[0].strip():
                target_ids.add(row[0].strip())

    logger.info(f"🎯 Loaded {len(target_ids):,} target ArXiv IDs")
    return target_ids


def parse_manifest(manifest_file: str) -> List[Dict]:
    """Parse the ArXiv PDF manifest XML file."""
    tree = ET.parse(manifest_file)
    root = tree.getroot()

    files = []
    for file_elem in root.findall("file"):
        file_info = {
            "filename": file_elem.find("filename").text,
            "first_item": file_elem.find("first_item").text,
            "last_item": file_elem.find("last_item").text,
            "num_items": int(file_elem.find("num_items").text),
            "size": int(file_elem.find("size").text),
            "yymm": file_elem.find("yymm").text,
            "md5sum": file_elem.find("md5sum").text,
        }
        files.append(file_info)

    logger.info(f"📊 Parsed manifest: {len(files)} tar files available")
    return files


def estimate_paper_overlap(file_info: Dict, target_ids: Set[str]) -> int:
    """Estimate how many target papers might be in this file."""
    first_id = file_info["first_item"]
    last_id = file_info["last_item"]

    # Count target IDs that fall in this range
    overlap_count = 0
    for target_id in target_ids:
        if first_id <= target_id <= last_id:
            overlap_count += 1

    return overlap_count


def create_download_plan(
    manifest_files: List[Dict], target_ids: Set[str], max_cost: float = 50.0
) -> Dict:
    """Create an optimized download plan within budget."""

    # Calculate efficiency for each file (papers per GB)
    file_efficiency = []

    for file_info in manifest_files:
        overlap = estimate_paper_overlap(file_info, target_ids)
        if overlap > 0:
            size_gb = file_info["size"] / (1024**3)
            efficiency = overlap / size_gb  # papers per GB

            file_efficiency.append(
                {
                    "file_info": file_info,
                    "overlap": overlap,
                    "size_gb": size_gb,
                    "efficiency": efficiency,
                    "cost": size_gb * 0.09,
                }
            )

    # Sort by efficiency (most papers per GB first)
    file_efficiency.sort(key=lambda x: x["efficiency"], reverse=True)

    # Select files within budget
    selected_files = []
    total_cost = 0.0
    total_papers = 0
    covered_papers = set()

    for file_data in file_efficiency:
        if total_cost + file_data["cost"] <= max_cost:
            selected_files.append(file_data)
            total_cost += file_data["cost"]
            total_papers += file_data["overlap"]

            # Track which papers we're covering (approximate)
            file_info = file_data["file_info"]
            first_id = file_info["first_item"]
            last_id = file_info["last_item"]

            for target_id in target_ids:
                if first_id <= target_id <= last_id:
                    covered_papers.add(target_id)

    return {
        "selected_files": selected_files,
        "total_cost": total_cost,
        "total_papers_estimated": total_papers,
        "coverage_percentage": len(covered_papers) / len(target_ids) * 100,
        "covered_papers": len(covered_papers),
        "total_size_gb": sum(f["size_gb"] for f in selected_files),
    }


def analyze_year_distribution(target_ids: Set[str]) -> Dict:
    """Analyze the year distribution of target papers."""
    year_counts = defaultdict(int)

    for arxiv_id in target_ids:
        # Extract year from ArXiv ID (e.g., "2302.11211" -> 2023)
        if "." in arxiv_id:
            year_month = arxiv_id.split(".")[0]
            if len(year_month) == 4:  # Format: YYMM
                if year_month.startswith("9"):  # 91xx = 19xx
                    year = f"19{year_month[:2]}"
                else:  # 00xx, 23xx = 20xx
                    year = f"20{year_month[:2]}"
                year_counts[year] += 1

    return dict(year_counts)


def main():
    """Main planning function."""
    import argparse

    parser = argparse.ArgumentParser(description="Smart ArXiv Download Planner")
    parser.add_argument(
        "--csv",
        default="data/arxiv_papers_hf.csv",
        help="CSV file with target ArXiv IDs",
    )
    parser.add_argument(
        "--manifest", default="arXiv_pdf_manifest.xml", help="ArXiv PDF manifest file"
    )
    parser.add_argument(
        "--budget", type=float, default=50.0, help="Maximum budget in USD"
    )

    args = parser.parse_args()

    if not Path(args.manifest).exists():
        print(f"❌ Manifest file not found: {args.manifest}")
        return

    # Load data
    target_ids = load_target_arxiv_ids(args.csv)
    manifest_files = parse_manifest(args.manifest)

    # Analyze target papers
    year_dist = analyze_year_distribution(target_ids)

    # Create download plan
    plan = create_download_plan(manifest_files, target_ids, args.budget)

    # Display results
    print("\n" + "=" * 60)
    print("🎯 SMART ARXIV DOWNLOAD PLAN")
    print("=" * 60)
    print(f"📊 Target papers: {len(target_ids):,}")
    print(f"💰 Budget limit: ${args.budget:.2f}")
    print(f"📦 Recommended files: {len(plan['selected_files'])}")
    print(f"💾 Total download: {plan['total_size_gb']:.2f} GB")
    print(f"💸 Estimated cost: ${plan['total_cost']:.2f}")
    print(
        f"📈 Coverage: {plan['coverage_percentage']:.1f}% ({plan['covered_papers']:,} papers)"
    )

    print("\n📅 YOUR PAPERS BY YEAR:")
    for year in sorted(year_dist.keys()):
        print(f"   {year}: {year_dist[year]:,} papers")

    print("\n🏆 TOP 10 MOST EFFICIENT FILES:")
    for i, file_data in enumerate(plan["selected_files"][:10]):
        file_info = file_data["file_info"]
        print(f"   {i + 1:2d}. {file_info['filename']}")
        print(
            f"       📊 ~{file_data['overlap']} papers, {file_data['size_gb']:.2f} GB, ${file_data['cost']:.2f}"
        )
        print(f"       ⚡ {file_data['efficiency']:.1f} papers/GB")

    if len(plan["selected_files"]) > 10:
        print(f"       ... and {len(plan['selected_files']) - 10} more files")

    print("\n💡 RECOMMENDATIONS:")

    if plan["coverage_percentage"] < 50:
        print(
            f"⚠️  Low coverage ({plan['coverage_percentage']:.1f}%) with ${args.budget} budget"
        )
        print("💰 Consider increasing budget to $100-200 for better coverage")

        # Try higher budget
        better_plan = create_download_plan(manifest_files, target_ids, 100.0)
        print(
            f"📈 With $100 budget: {better_plan['coverage_percentage']:.1f}% coverage, {better_plan['total_size_gb']:.1f} GB"
        )

    elif plan["coverage_percentage"] > 80:
        print(
            f"✅ Excellent coverage ({plan['coverage_percentage']:.1f}%) within budget!"
        )
        print("🚀 This plan will get you most of your target papers efficiently")

    else:
        print(f"👍 Good coverage ({plan['coverage_percentage']:.1f}%) within budget")
        print("💡 Consider slight budget increase for better coverage")

    print("\n🔥 ALTERNATIVE STRATEGIES:")
    print("1. 🎯 Focus on recent papers (2020+): Lower cost, high relevance")
    print("2. 📊 Download by year: Spread cost over time")
    print(
        "3. 🔍 Individual downloads: Use original rate-limited approach for specific papers"
    )
    print("4. 🤝 Collaborate: Split costs with others who need ArXiv papers")

    print("=" * 60)


if __name__ == "__main__":
    main()
