#!/usr/bin/env python3
"""
Hybrid ArXiv Downloader - uses HTTP for manifest, S3 for PDFs
Fallback approach if S3 permissions are tricky
"""

import requests
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_manifest_http():
    """Download manifest via HTTP as fallback."""
    # Try different possible URLs for the manifest
    urls = [
        "https://arxiv.org/pdf/arXiv_pdf_manifest.xml",
        "https://s3.amazonaws.com/arxiv/pdf/arXiv_pdf_manifest.xml",
        "https://arxiv.s3.amazonaws.com/pdf/arXiv_pdf_manifest.xml",
    ]

    for url in urls:
        try:
            logger.info(f"Trying to download manifest from: {url}")
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                logger.info(f"✅ Successfully downloaded manifest from {url}")
                logger.info(f"   Size: {len(response.content)} bytes")

                # Save to file
                manifest_path = Path("arXiv_pdf_manifest.xml")
                with open(manifest_path, "wb") as f:
                    f.write(response.content)

                return True
            else:
                logger.info(f"❌ Failed: HTTP {response.status_code}")

        except Exception as e:
            logger.info(f"❌ Error: {e}")

    return False


if __name__ == "__main__":
    success = download_manifest_http()
    if success:
        print("🎉 Manifest downloaded successfully!")
        print("Now we can parse it and see what's available")
    else:
        print("❌ Could not download manifest via HTTP")
