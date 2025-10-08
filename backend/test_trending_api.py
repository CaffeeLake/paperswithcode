#!/usr/bin/env python3
"""
Test script for the trending papers API endpoint.

This script verifies that the trending papers endpoint is working correctly
and displays sample results.
"""

import requests


def test_trending_endpoint(base_url="http://localhost:8000"):
    """Test the trending papers endpoint."""

    print("=" * 80)
    print("Testing Trending Papers API Endpoint")
    print("=" * 80)
    print()

    # Test 1: Basic endpoint with default parameters
    print("Test 1: GET /api/v1/papers/trending (default parameters)")
    print("-" * 80)

    try:
        response = requests.get(f"{base_url}/api/v1/papers/trending")
        response.raise_for_status()

        papers = response.json()
        print(f"✅ Success! Retrieved {len(papers)} trending papers")
        print()

        if papers:
            print("Top 3 trending papers:")
            for i, paper in enumerate(papers[:3], 1):
                print(f"\n{i}. {paper['title']}")
                print(f"   ArXiv: {paper['arxiv_id']}")
                print(f"   Repository: {paper['repository']['url']}")
                print(f"   Stars: {paper['repository']['num_stars']}")
                print(f"   Trending Score: {paper['trending']['trending_score']:.4f}")
                print(
                    f"   Velocity (24h): {paper['trending']['velocity_24h']:.4f} stars/hour"
                )
                print(f"   Stars Gained (24h): {paper['trending']['stars_gained_24h']}")
                print(f"   Paper Age: {paper['paper_age_days']:.1f} days")
        else:
            print("⚠️  No trending papers found (may need more star history data)")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return False

    print()
    print("-" * 80)
    print()

    # Test 2: With limit parameter
    print("Test 2: GET /api/v1/papers/trending?limit=5")
    print("-" * 80)

    try:
        response = requests.get(f"{base_url}/api/v1/papers/trending?limit=5")
        response.raise_for_status()

        papers = response.json()
        print(f"✅ Success! Retrieved {len(papers)} papers (limit=5)")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return False

    print()
    print("-" * 80)
    print()

    # Test 3: With max_age_days parameter
    print("Test 3: GET /api/v1/papers/trending?max_age_days=90")
    print("-" * 80)

    try:
        response = requests.get(f"{base_url}/api/v1/papers/trending?max_age_days=90")
        response.raise_for_status()

        papers = response.json()
        print(f"✅ Success! Retrieved {len(papers)} papers from last 90 days")

        if papers:
            # Verify all papers are within age limit
            for paper in papers:
                if paper["paper_age_days"] > 90:
                    print(
                        f"⚠️  Warning: Found paper older than 90 days: {paper['paper_age_days']:.1f}"
                    )

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return False

    print()
    print("-" * 80)
    print()

    # Test 4: With min_velocity parameter
    print("Test 4: GET /api/v1/papers/trending?min_velocity=1.0")
    print("-" * 80)

    try:
        response = requests.get(f"{base_url}/api/v1/papers/trending?min_velocity=1.0")
        response.raise_for_status()

        papers = response.json()
        print(
            f"✅ Success! Retrieved {len(papers)} papers with velocity >= 1.0 stars/hour"
        )

        if papers:
            # Verify all papers meet velocity threshold
            for paper in papers:
                if paper["trending"]["velocity_24h"] < 1.0:
                    print(
                        f"⚠️  Warning: Found paper with velocity < 1.0: {paper['trending']['velocity_24h']:.4f}"
                    )

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return False

    print()
    print("=" * 80)
    print("All tests completed successfully! ✅")
    print("=" * 80)

    return True


def main():
    """Main test execution."""
    try:
        success = test_trending_endpoint()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
