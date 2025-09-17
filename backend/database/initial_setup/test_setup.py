#!/usr/bin/env python3
"""
Test script to verify database setup and import script functionality.
"""

import json
import os
import sys


# Test if we can load the JSON file structure
def test_json_loading():
    """Test loading a small sample of the JSON data."""
    json_path = "../data/papers-with-abstracts.json"

    if not os.path.exists(json_path):
        print("❌ Papers JSON file not found at:", json_path)
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            # Read just the first few characters to test file access
            sample = f.read(1000)
            if sample.startswith("["):
                print("✅ JSON file is accessible and appears to be valid")
                return True
            else:
                print("❌ JSON file doesn't start with expected '[' character")
                return False
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return False


# Test database connection requirements
def test_database_requirements():
    """Test if required database packages are available."""
    import importlib.util

    if importlib.util.find_spec("psycopg2") is not None:
        print("✅ psycopg2 package is available")
        return True
    else:
        print("❌ psycopg2 package not found. Run: pip install psycopg2-binary")
        return False


# Test a small sample import (without database connection)
def test_data_processing():
    """Test processing a small sample of papers data."""
    json_path = "../data/papers-with-abstracts.json"

    if not os.path.exists(json_path):
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            # Load just first few papers for testing
            content = f.read()
            # Find the first complete paper entry
            papers = json.loads(content)

            if len(papers) > 0:
                sample_paper = papers[0]

                # Test key fields exist
                required_fields = ["title", "paper_url", "authors"]
                missing_fields = []

                for field in required_fields:
                    if field not in sample_paper:
                        missing_fields.append(field)

                if missing_fields:
                    print(f"❌ Sample paper missing fields: {missing_fields}")
                    return False
                else:
                    print("✅ Sample paper has all required fields")
                    print(f"   Title: {sample_paper['title'][:60]}...")
                    print(f"   Authors: {len(sample_paper['authors'])} authors")
                    print(f"   Date: {sample_paper.get('date', 'N/A')}")
                    return True
            else:
                print("❌ No papers found in JSON file")
                return False

    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error processing data: {e}")
        return False


def main():
    """Run all tests."""
    print("🔍 Testing PapersWithCode Database Setup")
    print("=" * 50)

    tests = [
        ("JSON File Access", test_json_loading),
        ("Database Requirements", test_database_requirements),
        ("Data Processing", test_data_processing),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n📋 Testing: {test_name}")
        result = test_func()
        results.append(result)

    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")

    passed = sum(results)
    total = len(results)

    for i, (test_name, _) in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"   {test_name}: {status}")

    print(f"\n📈 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! You're ready to set up the database.")
        print("\nNext steps:")
        print("1. Make sure PostgreSQL is installed and running")
        print("2. Create the database: CREATE DATABASE paperswithcode;")
        print(
            "3. Run the schema setup: psql -U postgres -d paperswithcode -f setup_database.sql"
        )
        print("4. Import the papers: python import_papers.py")
    else:
        print(
            f"\n⚠️  {total - passed} test(s) failed. Please fix the issues above before proceeding."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
