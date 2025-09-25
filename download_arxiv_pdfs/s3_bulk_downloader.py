#!/usr/bin/env python3
"""
ArXiv S3 Bulk PDF Downloader

Downloads PDFs directly from ArXiv's Amazon S3 bucket, avoiding rate limits.
Based on: https://info.arxiv.org/help/bulk_data_s3.html
"""

import csv
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import logging
from typing import List, Set, Dict, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("arxiv_s3_download.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class ArxivS3Downloader:
    """Downloads PDFs from ArXiv's S3 bucket."""

    def __init__(self, output_dir: str = "arxiv_pdfs/downloaded"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ArXiv S3 bucket (requester pays)
        self.bucket_name = "arxiv"
        self.region = "us-east-1"  # N. Virginia region

        # Initialize S3 client
        self.s3_client = None
        self.setup_s3_client()

        # Manifest data
        self.manifest_data = None

    def setup_s3_client(self):
        """Setup S3 client with requester pays configuration."""
        try:
            # Try to create S3 client
            self.s3_client = boto3.client("s3", region_name=self.region)

            # Test credentials by listing bucket (this will fail gracefully)
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info("✅ AWS credentials configured successfully")
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "403":
                    logger.info(
                        "✅ AWS credentials found (bucket access restricted as expected)"
                    )
                else:
                    logger.warning(f"AWS credentials issue: {e}")

        except NoCredentialsError:
            logger.error("❌ No AWS credentials found!")
            logger.error("Please configure AWS credentials:")
            logger.error("1. Run: aws configure")
            logger.error(
                "2. Or set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
            )
            self.s3_client = None
        except Exception as e:
            logger.error(f"Error setting up S3 client: {e}")
            self.s3_client = None

    def check_aws_setup(self) -> bool:
        """Check if AWS is properly configured."""
        if not self.s3_client:
            return False

        # Skip the list test - it often fails due to permissions
        # We'll test by trying to download the manifest directly
        logger.info("✅ AWS S3 client configured - will test with manifest download")
        return True

    def download_manifest(self) -> bool:
        """Download the PDF manifest file."""
        manifest_key = "pdf/arXiv_pdf_manifest.xml"
        manifest_path = self.output_dir / "arXiv_pdf_manifest.xml"

        try:
            logger.info("📋 Downloading PDF manifest...")

            self.s3_client.download_file(
                Bucket=self.bucket_name,
                Key=manifest_key,
                Filename=str(manifest_path),
                ExtraArgs={"RequestPayer": "Requester"},
            )

            logger.info(f"✅ Downloaded manifest to {manifest_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to download manifest: {e}")
            return False

    def parse_manifest(self) -> List[Dict]:
        """Parse the XML manifest file."""
        manifest_path = self.output_dir / "arXiv_pdf_manifest.xml"

        if not manifest_path.exists():
            logger.error("Manifest file not found. Download it first.")
            return []

        try:
            tree = ET.parse(manifest_path)
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
            self.manifest_data = files
            return files

        except Exception as e:
            logger.error(f"Error parsing manifest: {e}")
            return []

    def load_target_arxiv_ids(self, csv_file: str) -> Set[str]:
        """Load the ArXiv IDs we want to download."""
        target_ids = set()

        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)

                for row in reader:
                    if row and row[0].strip():
                        arxiv_id = row[0].strip()
                        target_ids.add(arxiv_id)

            logger.info(f"🎯 Loaded {len(target_ids):,} target ArXiv IDs")
            return target_ids

        except Exception as e:
            logger.error(f"Error loading target IDs: {e}")
            return set()

    def find_relevant_tar_files(self, target_ids: Set[str]) -> List[Dict]:
        """Find which tar files might contain our target PDFs."""
        if not self.manifest_data:
            logger.error("No manifest data available")
            return []

        relevant_files = []

        # For each tar file, check if it might contain any of our target IDs
        for file_info in self.manifest_data:
            first_id = file_info["first_item"]
            last_id = file_info["last_item"]

            # Check if any target ID falls in the range
            might_contain_targets = False

            for target_id in target_ids:
                # Simple string comparison for ArXiv IDs
                if first_id <= target_id <= last_id:
                    might_contain_targets = True
                    break

            if might_contain_targets:
                relevant_files.append(file_info)

        logger.info(f"📦 Found {len(relevant_files)} potentially relevant tar files")
        return relevant_files

    def download_and_extract_tar(self, file_info: Dict, target_ids: Set[str]) -> int:
        """Download a tar file and extract only the PDFs we need."""
        tar_key = file_info["filename"]
        tar_filename = Path(tar_key).name

        logger.info(
            f"📥 Processing {tar_filename} ({file_info['num_items']:,} PDFs, {file_info['size'] / 1024 / 1024:.1f} MB)"
        )

        extracted_count = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_tar_path = Path(temp_dir) / tar_filename

            try:
                # Download tar file
                logger.info(f"   ⬇️  Downloading {tar_filename}...")
                self.s3_client.download_file(
                    Bucket=self.bucket_name,
                    Key=tar_key,
                    Filename=str(temp_tar_path),
                    ExtraArgs={"RequestPayer": "Requester"},
                )

                # Extract and filter PDFs
                logger.info("   📂 Extracting relevant PDFs...")
                with tarfile.open(temp_tar_path, "r") as tar:
                    for member in tar.getmembers():
                        if member.isfile() and member.name.endswith(".pdf"):
                            # Extract ArXiv ID from filename
                            pdf_name = Path(member.name).name
                            arxiv_id = pdf_name.replace(".pdf", "")

                            if arxiv_id in target_ids:
                                # Extract this PDF
                                output_path = self.output_dir / pdf_name

                                if not output_path.exists():
                                    with tar.extractfile(member) as source:
                                        with open(output_path, "wb") as dest:
                                            dest.write(source.read())

                                    extracted_count += 1
                                    if extracted_count % 10 == 0:
                                        logger.info(
                                            f"      ✅ Extracted {extracted_count} PDFs so far..."
                                        )
                                else:
                                    logger.debug(
                                        f"      ⏭️  Skipped {arxiv_id} (already exists)"
                                    )

                logger.info(
                    f"   🎉 Extracted {extracted_count} PDFs from {tar_filename}"
                )

            except Exception as e:
                logger.error(f"❌ Error processing {tar_filename}: {e}")

        return extracted_count

    def estimate_costs(self, relevant_files: List[Dict]) -> Dict:
        """Estimate AWS costs for downloading."""
        total_size_gb = sum(f["size"] for f in relevant_files) / (1024**3)

        # AWS S3 pricing (approximate, as of 2024)
        # Data transfer out from US East: ~$0.09 per GB
        estimated_cost = total_size_gb * 0.09

        return {
            "total_files": len(relevant_files),
            "total_size_gb": total_size_gb,
            "estimated_cost_usd": estimated_cost,
        }

    def download_pdfs(self, csv_file: str, max_files: Optional[int] = None) -> Dict:
        """Main function to download PDFs from S3."""

        # Check AWS setup
        if not self.check_aws_setup():
            return {"error": "AWS not properly configured"}

        # Download and parse manifest
        if not self.download_manifest():
            return {"error": "Failed to download manifest"}

        if not self.parse_manifest():
            return {"error": "Failed to parse manifest"}

        # Load target IDs
        target_ids = self.load_target_arxiv_ids(csv_file)
        if not target_ids:
            return {"error": "No target ArXiv IDs found"}

        # Find relevant tar files
        relevant_files = self.find_relevant_tar_files(target_ids)
        if not relevant_files:
            return {"error": "No relevant tar files found"}

        # Estimate costs
        cost_estimate = self.estimate_costs(relevant_files)
        logger.info("=" * 60)
        logger.info("💰 COST ESTIMATE")
        logger.info(f"Target ArXiv IDs: {len(target_ids):,}")
        logger.info(f"Files to download: {cost_estimate['total_files']}")
        logger.info(f"Total size: {cost_estimate['total_size_gb']:.2f} GB")
        logger.info(f"Estimated cost: ${cost_estimate['estimated_cost_usd']:.2f} USD")
        logger.info("=" * 60)

        # Limit files if requested
        if max_files:
            relevant_files = relevant_files[:max_files]
            logger.info(f"🧪 Limited to first {max_files} files for testing")

        # Download and extract
        total_extracted = 0
        for i, file_info in enumerate(relevant_files, 1):
            logger.info(f"📦 Processing file {i}/{len(relevant_files)}")
            extracted = self.download_and_extract_tar(file_info, target_ids)
            total_extracted += extracted

            if extracted > 0:
                logger.info(f"✅ Total extracted so far: {total_extracted:,} PDFs")

        return {
            "success": True,
            "total_extracted": total_extracted,
            "files_processed": len(relevant_files),
            "cost_estimate": cost_estimate,
        }


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv S3 Bulk PDF Downloader")
    parser.add_argument(
        "--csv",
        default="data/arxiv_papers_hf.csv",
        help="CSV file with ArXiv IDs to download",
    )
    parser.add_argument(
        "--output-dir",
        default="arxiv_pdfs/downloaded",
        help="Output directory for PDFs",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of tar files to process (for testing)",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Only show cost estimate, don't download",
    )

    args = parser.parse_args()

    downloader = ArxivS3Downloader(args.output_dir)

    if args.estimate_only:
        # Just show cost estimate
        if downloader.check_aws_setup():
            downloader.download_manifest()
            downloader.parse_manifest()
            target_ids = downloader.load_target_arxiv_ids(args.csv)
            relevant_files = downloader.find_relevant_tar_files(target_ids)
            cost_estimate = downloader.estimate_costs(relevant_files)

            print("\n💰 COST ESTIMATE:")
            print(f"Target ArXiv IDs: {len(target_ids):,}")
            print(f"Relevant tar files: {cost_estimate['total_files']}")
            print(f"Total download size: {cost_estimate['total_size_gb']:.2f} GB")
            print(f"Estimated AWS cost: ${cost_estimate['estimated_cost_usd']:.2f} USD")
        return

    # Start download
    result = downloader.download_pdfs(args.csv, args.max_files)

    if result.get("success"):
        print("\n🎉 DOWNLOAD COMPLETE!")
        print(f"PDFs extracted: {result['total_extracted']:,}")
        print(f"Files processed: {result['files_processed']}")
        print(f"Output directory: {args.output_dir}")
        if result.get("cost_estimate"):
            print(
                f"Estimated cost: ${result['cost_estimate']['estimated_cost_usd']:.2f} USD"
            )
    else:
        print(f"\n❌ Download failed: {result.get('error')}")


if __name__ == "__main__":
    main()
