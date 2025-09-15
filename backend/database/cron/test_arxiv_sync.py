#!/usr/bin/env python3
"""
Test script for ArXiv sync functionality using the Database class.
Tests the sync with a small date range to verify everything works.
"""

import sys
import os
from datetime import date, timedelta

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.arxiv_sync import ArXivSyncer
from database.db_connection import PapersDatabase, DatabaseConfig


def test_database_connection():
    """Test the database connection and basic operations."""
    print("🔌 Testing database connection...")
    
    db = PapersDatabase()
    
    try:
        if not db.test_connection():
            print("❌ Database connection failed")
            return False
        
        print("✅ Database connection successful")
        
        # Test basic operations
        paper_count = db.get_paper_count()
        latest_date = db.get_latest_paper_date()
        
        print(f"📊 Total papers in database: {paper_count:,}")
        print(f"📅 Latest paper date: {latest_date}")
        
        # Test search functionality
        search_results = db.search_papers("neural network", limit=3)
        print(f"🔍 Search test: Found {len(search_results)} papers for 'neural network'")
        
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False
    finally:
        db.disconnect()


def test_arxiv_sync():
    """Test the ArXiv sync with a small date range."""
    print("\n🧪 Testing ArXiv sync functionality...")
    
    # Create syncer
    syncer = ArXivSyncer()
    
    # Test with a small date range (last 3 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=3)
    
    print(f"📅 Testing sync for date range: {start_date} to {end_date}")
    
    try:
        # Test ArXiv API fetch (without inserting)
        print("🌐 Testing ArXiv API fetch...")
        papers = syncer.fetch_arxiv_papers(start_date, end_date)
        print(f"✅ Fetched {len(papers)} papers from ArXiv API")
        
        if papers:
            sample_paper = papers[0]
            print(f"📄 Sample paper: {sample_paper['title'][:60]}...")
            print(f"   ArXiv ID: {sample_paper['arxiv_id']}")
            print(f"   Version: {sample_paper['version']}")
            print(f"   Date: {sample_paper['date_published']}")
        
        # Test full sync (this will actually insert papers)
        print("💾 Testing full sync to database...")
        results = syncer.sync_papers(start_date, end_date)
        
        print("✅ Sync test completed successfully!")
        print(f"📊 Results: {results}")
        
        return True
        
    except Exception as e:
        print(f"❌ ArXiv sync test failed: {e}")
        return False


def test_specific_date():
    """Test sync for a specific date with known papers."""
    print("\n🎯 Testing sync for a specific date (2025-09-01)...")
    
    syncer = ArXivSyncer()
    test_date = date(2025, 9, 1)
    
    try:
        results = syncer.sync_papers(test_date, test_date)
        print(f"✅ Specific date sync completed: {results}")
        return True
    except Exception as e:
        print(f"❌ Specific date test failed: {e}")
        return False


def test_database_methods():
    """Test various database methods."""
    print("\n🧮 Testing database methods...")
    
    db = PapersDatabase()
    
    try:
        # Test version distribution
        version_dist = db.get_version_distribution()
        print(f"📊 Version distribution: {len(version_dist)} different versions")
        for v in version_dist[:5]:  # Show top 5
            print(f"   {v['version']}: {v['count']} papers ({v['percentage']}%)")
        
        # Test year distribution
        year_2024 = db.get_papers_by_year(2024)
        print(f"📅 2024 monthly distribution: {len(year_2024)} months with data")
        
        # Test paper existence check
        exists = db.paper_exists("1706.03762", "v1")  # Transformer paper
        print(f"🔍 Transformer paper exists: {exists}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database methods test failed: {e}")
        return False
    finally:
        db.disconnect()


if __name__ == "__main__":
    print("🚀 ArXiv Sync Test Suite (Refactored)")
    print("=" * 60)
    
    # Run tests
    test1_passed = test_database_connection()
    test2_passed = test_arxiv_sync()
    test3_passed = test_specific_date()
    test4_passed = test_database_methods()
    
    print("\n" + "=" * 60)
    if all([test1_passed, test2_passed, test3_passed, test4_passed]):
        print("🎉 All tests passed! ArXiv sync is ready for production.")
        print("\nNext steps:")
        print("1. Run: chmod +x backend/database/setup_cron.sh")
        print("2. Run: ./backend/database/setup_cron.sh")
        print("3. Monitor logs: tail -f backend/database/arxiv_sync.log")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        sys.exit(1)