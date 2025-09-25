#!/usr/bin/env python3
"""
ArXiv S3 Cost Estimator

Analyzes the downloaded manifest to estimate costs for downloading specific papers.
"""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
import logging
from typing import Set, List, Dict

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


def find_relevant_files(manifest_files: List[Dict], target_ids: Set[str]) -> List[Dict]:
    """Find tar files that might contain our target papers."""
    relevant_files = []

    for file_info in manifest_files:
        first_id = file_info["first_item"]
        last_id = file_info["last_item"]

        # Check if any target ID falls in this range
        # This is a heuristic - some files might not contain our papers
        might_contain_targets = False

        for target_id in target_ids:
            # Simple string comparison for ArXiv IDs
            if first_id <= target_id <= last_id:
                might_contain_targets = True
                break

        if might_contain_targets:
            relevant_files.append(file_info)

    return relevant_files


def estimate_costs(relevant_files: List[Dict]) -> Dict:
    """Estimate AWS costs for downloading."""
    total_size_bytes = sum(f["size"] for f in relevant_files)
    total_size_gb = total_size_bytes / (1024**3)

    # AWS S3 pricing (approximate)
    cost_per_gb = 0.09  # $0.09 per GB for data transfer out
    estimated_cost = total_size_gb * cost_per_gb

    return {
        "total_files": len(relevant_files),
        "total_size_bytes": total_size_bytes,
        "total_size_gb": total_size_gb,
        "estimated_cost_usd": estimated_cost,
        "cost_per_gb": cost_per_gb,
    }


def analyze_by_year(relevant_files: List[Dict]) -> Dict:
    """Analyze files by year to understand the distribution."""
    by_year = {}

    for file_info in relevant_files:
        yymm = file_info["yymm"]

        # Convert yymm to year
        if yymm.startswith("9"):  # 91xx = 19xx
            year = f"19{yymm[:2]}"
        else:  # 00xx = 20xx, 25xx = 20xx
            year = f"20{yymm[:2]}"

        if year not in by_year:
            by_year[year] = {"files": 0, "size": 0, "papers": 0}

        by_year[year]["files"] += 1
        by_year[year]["size"] += file_info["size"]
        by_year[year]["papers"] += file_info["num_items"]

    return by_year


def main():
    """Main analysis function."""
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv S3 Cost Estimator")
    parser.add_argument(
        "--csv",
        default="data/arxiv_papers_hf.csv",
        help="CSV file with target ArXiv IDs",
    )
    parser.add_argument(
        "--manifest", default="arXiv_pdf_manifest.xml", help="ArXiv PDF manifest file"
    )

    args = parser.parse_args()

    if not Path(args.manifest).exists():
        print(f"❌ Manifest file not found: {args.manifest}")
        print(
            "Download it first with: uv run s3cmd get s3://arxiv/pdf/arXiv_pdf_manifest.xml --requester-pays"
        )
        return

    # Load data
    target_ids = load_target_arxiv_ids(args.csv)
    manifest_files = parse_manifest(args.manifest)
    relevant_files = find_relevant_files(manifest_files, target_ids)

    if not relevant_files:
        print("❌ No relevant files found for your target papers")
        return

    # Calculate costs
    costs = estimate_costs(relevant_files)
    year_analysis = analyze_by_year(relevant_files)

    # Display results
    print("\n" + "=" * 60)
    print("📊 ARXIV S3 DOWNLOAD ANALYSIS")
    print("=" * 60)
    print(f"🎯 Target ArXiv papers: {len(target_ids):,}")
    print(f"📦 Relevant tar files: {costs['total_files']:,}")
    print(f"💾 Total download size: {costs['total_size_gb']:.2f} GB")
    print(f"💰 Estimated cost: ${costs['estimated_cost_usd']:.2f} USD")
    print(f"📈 Cost per GB: ${costs['cost_per_gb']:.2f}")

    print("\n📅 DISTRIBUTION BY YEAR:")
    for year in sorted(year_analysis.keys()):
        data = year_analysis[year]
        size_gb = data["size"] / (1024**3)
        print(
            f"   {year}: {data['files']:3d} files, {size_gb:6.2f} GB, ~{data['papers']:,} papers"
        )

    print("\n🔍 SAMPLE FILES TO DOWNLOAD:")
    for i, file_info in enumerate(relevant_files[:5]):
        size_mb = file_info["size"] / (1024**2)
        print(
            f"   {i + 1}. {file_info['filename']} ({size_mb:.1f} MB, {file_info['num_items']} papers)"
        )

    if len(relevant_files) > 5:
        print(f"   ... and {len(relevant_files) - 5} more files")

    print("\n🚀 NEXT STEPS:")
    print("1. This is much cheaper than VPN/VPS alternatives!")
    print(
        "2. Download command: uv run s3cmd get s3://arxiv/pdf/FILENAME --requester-pays"
    )
    print("3. Extract only your target papers from each tar file")
    print("4. Total time estimate: 2-6 hours depending on connection speed")
    print("=" * 60)


if __name__ == "__main__":
    main()
