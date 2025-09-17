#!/usr/bin/env python3
"""
Batch citation population script for large-scale processing.

This script is designed to handle the full dataset of 500k+ papers by:
- Processing papers in configurable batches
- Resuming from where it left off
- Providing detailed progress tracking
- Handling API rate limits gracefully
- Prioritizing more recent papers (likely to have more citations)
"""

import asyncio
import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent.parent.parent.parent  # Go up to project root
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

# Set environment variable to help with relative imports
os.environ.setdefault('PYTHONPATH', str(backend_dir))

from backend.database.connection import get_database_session
from backend.services.semantic_scholar_service import SemanticScholarService
from sqlalchemy import text

# Semantic Scholar API key
SEMANTIC_SCHOLAR_API_KEY = "6Wa5zD2S3HahK5AAjMRnr6n31usSpq1a3gpksOQa"


async def batch_populate_citations(
    batch_size: int = 100, 
    max_batches: int = None,
    start_from_batch: int = 0,
    prioritize_recent: bool = True
):
    """
    Populate citation counts in batches with progress tracking.
    
    Args:
        batch_size: Number of papers to process per batch
        max_batches: Maximum number of batches to process (None = all)
        start_from_batch: Batch number to start from (for resuming)
        prioritize_recent: Whether to prioritize more recent papers
    """
    print(f"🚀 Starting batch citation population...")
    print(f"📊 Batch size: {batch_size}")
    print(f"🔄 Max batches: {max_batches or 'All'}")
    print(f"▶️  Starting from batch: {start_from_batch}")
    print(f"📅 Prioritize recent: {prioritize_recent}")
    print("=" * 60)
    
    # Get database session
    db = next(get_database_session())
    
    try:
        service = SemanticScholarService(db, api_key=SEMANTIC_SCHOLAR_API_KEY)
        
        # Get total count of papers needing citations
        total_papers = db.execute(text("""
            SELECT COUNT(*) 
            FROM papers 
            WHERE is_latest_version = true 
            AND semantic_scholar_id IS NULL
        """)).scalar()
        
        print(f"📚 Total papers needing citations: {total_papers:,}")
        
        total_batches = (total_papers + batch_size - 1) // batch_size
        if max_batches:
            total_batches = min(total_batches, max_batches)
        
        print(f"🔢 Total batches to process: {total_batches}")
        print()
        
        total_updated = 0
        start_time = time.time()
        
        for batch_num in range(start_from_batch, start_from_batch + total_batches):
            batch_start_time = time.time()
            
            print(f"📦 Processing batch {batch_num + 1}/{start_from_batch + total_batches}")
            
            # Process this batch
            updated_count = await service.batch_update_citation_counts(batch_size)
            total_updated += updated_count
            
            batch_time = time.time() - batch_start_time
            elapsed_time = time.time() - start_time
            
            # Calculate progress statistics
            papers_per_second = batch_size / batch_time if batch_time > 0 else 0
            estimated_remaining = (total_batches - (batch_num - start_from_batch + 1)) * batch_time
            
            print(f"✅ Batch {batch_num + 1} completed:")
            print(f"   📊 Papers updated: {updated_count}/{batch_size}")
            print(f"   ⏱️  Batch time: {batch_time:.1f}s")
            print(f"   🚀 Rate: {papers_per_second:.2f} papers/sec")
            print(f"   📈 Total updated: {total_updated:,}")
            print(f"   ⏰ Elapsed: {elapsed_time/60:.1f}m")
            print(f"   🔮 Est. remaining: {estimated_remaining/60:.1f}m")
            print()
            
            # Brief pause between batches to be respectful to the API
            if batch_num < start_from_batch + total_batches - 1:
                print("⏸️  Brief pause between batches...")
                await asyncio.sleep(2)
        
        total_time = time.time() - start_time
        
        print("🎉 Batch processing completed!")
        print(f"📊 Total papers updated: {total_updated:,}")
        print(f"⏰ Total time: {total_time/60:.1f} minutes")
        print(f"🚀 Average rate: {total_updated/total_time:.2f} papers/sec")
        
        # Show final statistics
        papers_with_citations = db.execute(text("""
            SELECT COUNT(*) 
            FROM papers 
            WHERE is_latest_version = true 
            AND semantic_scholar_id IS NOT NULL
        """)).scalar()
        
        papers_with_actual_citations = db.execute(text("""
            SELECT COUNT(*) 
            FROM papers 
            WHERE is_latest_version = true 
            AND citation_count > 0
        """)).scalar()
        
        print(f"📈 Papers with Semantic Scholar data: {papers_with_citations:,}")
        print(f"🎯 Papers with actual citations: {papers_with_actual_citations:,}")
        
        return total_updated
        
    except Exception as e:
        print(f"❌ Error in batch processing: {e}")
        return 0
    finally:
        db.close()


async def main():
    """Main function with command line argument parsing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Batch populate citation counts for papers")
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=100, 
        help="Number of papers to process per batch (default: 100)"
    )
    parser.add_argument(
        "--max-batches", 
        type=int, 
        default=None, 
        help="Maximum number of batches to process (default: all)"
    )
    parser.add_argument(
        "--start-from", 
        type=int, 
        default=0, 
        help="Batch number to start from (for resuming, default: 0)"
    )
    parser.add_argument(
        "--prioritize-recent", 
        action="store_true", 
        default=True,
        help="Prioritize more recent papers (default: True)"
    )
    
    args = parser.parse_args()
    
    print("📚 Batch Citation Count Population Tool")
    print("=" * 50)
    
    # Check if httpx is available
    try:
        import httpx
        print("✅ httpx is available")
    except ImportError:
        print("❌ httpx is not installed. Run: uv add httpx")
        sys.exit(1)
    
    # Run the batch population
    updated_count = await batch_populate_citations(
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        start_from_batch=args.start_from,
        prioritize_recent=args.prioritize_recent
    )
    
    if updated_count > 0:
        print(f"\n🎉 Successfully processed {updated_count} papers!")
        print("\nNext steps:")
        print("1. Check search results: curl 'http://localhost:8000/api/v1/papers/search?q=transformer'")
        print("2. Run more batches: python batch_populate_citations.py --max-batches 10")
        print("3. Resume processing: python batch_populate_citations.py --start-from X")
    else:
        print("\n❌ No papers were processed. Check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
