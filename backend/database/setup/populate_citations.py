#!/usr/bin/env python3
"""
Script to populate citation counts for existing papers in the database.

This script fetches citation counts from the Semantic Scholar API and updates
the database with the citation information.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent.parent.parent.parent  # Go up to project root
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

# Set environment variable to help with relative imports
os.environ.setdefault('PYTHONPATH', str(backend_dir))

from backend.database.connection import get_database_session
from backend.services.semantic_scholar_service import SemanticScholarService

# Semantic Scholar API key
SEMANTIC_SCHOLAR_API_KEY = "6Wa5zD2S3HahK5AAjMRnr6n31usSpq1a3gpksOQa"


async def populate_citations(limit: int = 50):
    """
    Populate citation counts for papers in the database.
    
    Args:
        limit: Maximum number of papers to update
    """
    print(f"🚀 Starting citation count population for up to {limit} papers...")
    
    # Get database session
    db = next(get_database_session())
    
    try:
        service = SemanticScholarService(db, api_key=SEMANTIC_SCHOLAR_API_KEY)
        
        print("📊 Updating citation counts from Semantic Scholar API...")
        print(f"🔑 Using API key for higher rate limits (1 req/sec)")
        updated_count = await service.batch_update_citation_counts(limit)
        
        print(f"✅ Successfully updated citation counts for {updated_count} papers!")
        
        if updated_count > 0:
            print("\n📈 Citation update summary:")
            print(f"  - Papers processed: {updated_count}")
            print(f"  - Rate limit respected: Yes")
            print(f"  - Database updated: Yes")
        
    except Exception as e:
        print(f"❌ Error populating citations: {e}")
        return False
    finally:
        db.close()
    
    return True


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Populate citation counts for papers")
    parser.add_argument(
        "--limit", 
        type=int, 
        default=50, 
        help="Maximum number of papers to update (default: 50)"
    )
    
    args = parser.parse_args()
    
    print("📚 Citation Count Population Tool")
    print("=" * 40)
    
    # Check if httpx is available
    try:
        import httpx
        print("✅ httpx is available")
    except ImportError:
        print("❌ httpx is not installed. Run: uv add httpx")
        sys.exit(1)
    
    # Run the population
    success = await populate_citations(args.limit)
    
    if success:
        print("\n🎉 Citation population completed successfully!")
        print("\nNext steps:")
        print("1. Test the enhanced search: python test_citation_search.py")
        print("2. Start the API server: python run_server.py")
        print("3. Try searching for 'vision transformer' to see citation-based ranking")
    else:
        print("\n❌ Citation population failed. Check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
