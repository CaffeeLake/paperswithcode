#!/usr/bin/env python3
"""
Test Direct ArXiv PDF Downloads

Check if we can download PDFs directly from ArXiv without getting HTML/captcha responses.
"""

import requests
import time
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_arxiv_pdf_download(arxiv_id: str, delay: float = 0) -> dict:
    """
    Test downloading a single PDF from ArXiv.

    Returns dict with test results.
    """
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # Use different user agents
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    try:
        if delay > 0:
            logger.info(f"Waiting {delay:.1f} seconds before request...")
            time.sleep(delay)

        logger.info(f"Testing download: {pdf_url}")

        response = requests.get(pdf_url, headers=headers, timeout=30)
        content = response.content

        # Analyze response
        is_pdf = content.startswith(b"%PDF-")
        is_html = (
            content[:100].lower().startswith(b"<!doctype html")
            or b"<html" in content[:500].lower()
        )
        is_captcha = any(
            indicator in content[:2000].lower()
            for indicator in [
                b"recaptcha",
                b"captcha",
                b"verify you are human",
                b"unusual traffic",
            ]
        )

        size_kb = len(content) / 1024

        result = {
            "arxiv_id": arxiv_id,
            "url": pdf_url,
            "status_code": response.status_code,
            "size_kb": size_kb,
            "is_pdf": is_pdf,
            "is_html": is_html,
            "is_captcha": is_captcha,
            "content_type": response.headers.get("content-type", "unknown"),
            "success": is_pdf and not is_captcha,
        }

        # Log result
        if result["success"]:
            logger.info(f"✅ SUCCESS: {arxiv_id} - PDF downloaded ({size_kb:.1f} KB)")
        elif is_captcha:
            logger.warning(f"❌ CAPTCHA: {arxiv_id} - Rate limited")
        elif is_html:
            logger.warning(f"❌ HTML: {arxiv_id} - Got HTML instead of PDF")
        else:
            logger.warning(f"❌ UNKNOWN: {arxiv_id} - Unexpected response")

        return result

    except Exception as e:
        logger.error(f"❌ ERROR: {arxiv_id} - {e}")
        return {"arxiv_id": arxiv_id, "error": str(e), "success": False}


def test_multiple_downloads():
    """Test downloading multiple PDFs with different strategies."""

    # Test papers from different time periods
    test_papers = [
        "2302.11211",  # Recent 2023
        "2401.12345",  # 2024 (if exists)
        "2012.15678",  # 2020
        "1706.03762",  # 2017 (Attention is All You Need - popular paper)
        "1912.11035",  # 2019
    ]

    results = []

    print("🧪 Testing ArXiv PDF Downloads")
    print("=" * 50)

    # Test 1: No delay
    print("\n📋 Test 1: Immediate downloads (no delay)")
    for i, arxiv_id in enumerate(test_papers):
        result = test_arxiv_pdf_download(arxiv_id, delay=0)
        results.append(result)
        if i < len(test_papers) - 1:  # Small delay between tests
            time.sleep(1)

    # Test 2: With delays
    print("\n📋 Test 2: Downloads with 5-second delays")
    for arxiv_id in test_papers[2:4]:  # Test 2 papers with delay
        result = test_arxiv_pdf_download(arxiv_id, delay=5)
        results.append(result)

    # Analyze results
    print("\n📊 RESULTS SUMMARY")
    print("=" * 50)

    successful = [r for r in results if r.get("success", False)]
    captcha_blocked = [r for r in results if r.get("is_captcha", False)]
    html_responses = [r for r in results if r.get("is_html", False)]
    errors = [r for r in results if "error" in r]

    print(f"✅ Successful downloads: {len(successful)}/{len(results)}")
    print(f"🚫 Captcha blocks: {len(captcha_blocked)}")
    print(f"🌐 HTML responses: {len(html_responses)}")
    print(f"❌ Errors: {len(errors)}")

    if successful:
        avg_size = sum(r["size_kb"] for r in successful) / len(successful)
        print(f"📊 Average PDF size: {avg_size:.1f} KB")

    print("\n💡 ANALYSIS:")

    if len(successful) >= len(results) * 0.8:
        print("🎉 ArXiv downloads are working well!")
        print(
            "   You can probably use direct downloads with conservative rate limiting"
        )
        print("   Recommended: 10-30 second delays between downloads")

    elif len(captcha_blocked) > len(successful):
        print("🚫 ArXiv is heavily rate limiting")
        print("   Your IP might be flagged from previous attempts")
        print("   Recommendations:")
        print("   1. Wait 24-48 hours before trying again")
        print("   2. Use VPN to change IP")
        print("   3. Stick with S3 bulk download approach")

    elif len(html_responses) > 0:
        print("🌐 Getting HTML responses instead of PDFs")
        print("   This might indicate soft rate limiting")
        print("   Try longer delays or different user agents")

    else:
        print("❓ Mixed results - might work with careful rate limiting")

    print("\n🎯 RECOMMENDATION FOR YOUR 80GB CONSTRAINT:")

    if len(successful) > 0:
        print("Since direct downloads might work:")
        print("1. 🎯 Download most important papers first (recent, high-citation)")
        print("2. 📊 Use 30-60 second delays to avoid rate limits")
        print("3. 💾 Download in batches of 1000-2000 papers (~10-20GB)")
        print("4. 🔄 Process and move completed papers to free up space")
    else:
        print("Since direct downloads are blocked:")
        print("1. 💰 Use S3 approach with $20-30 budget for most important papers")
        print("2. 📊 Focus on 2023-2024 papers (most recent and relevant)")
        print("3. 💾 Extract only your target papers from each tar file")
        print("4. 🗂️ Process in small batches to manage disk space")

    return results


if __name__ == "__main__":
    test_multiple_downloads()
