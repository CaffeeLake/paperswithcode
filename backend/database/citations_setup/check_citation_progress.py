#!/usr/bin/env python3
"""
Citation population progress checker.

This script provides detailed statistics about citation data population progress.
"""

import sys
from pathlib import Path

# Add the project root and backend directory to the Python path
project_root = Path(__file__).parent.parent.parent.parent  # Go up to project root
backend_dir = project_root / "backend"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

from backend.database.connection import get_database_session
from sqlalchemy import text


def check_citation_progress():
    """Check and display citation population progress."""
    print("📊 Citation Population Progress Report")
    print("=" * 50)
    
    db = next(get_database_session())
    
    try:
        # Basic statistics
        stats = db.execute(text("""
            SELECT 
                COUNT(*) as total_papers,
                COUNT(CASE WHEN semantic_scholar_id IS NOT NULL THEN 1 END) as papers_with_ss_id,
                COUNT(CASE WHEN citation_count > 0 THEN 1 END) as papers_with_citations,
                MAX(citation_count) as max_citations,
                AVG(CASE WHEN citation_count > 0 THEN citation_count END) as avg_citations
            FROM papers 
            WHERE is_latest_version = true
        """)).fetchone()
        
        total = stats.total_papers
        with_ss_id = stats.papers_with_ss_id
        with_citations = stats.papers_with_citations
        max_cites = stats.max_citations or 0
        avg_cites = stats.avg_citations or 0
        
        print(f"📚 Total papers (latest versions): {total:,}")
        print(f"🔍 Papers processed by Semantic Scholar: {with_ss_id:,}")
        print(f"📈 Papers with actual citations: {with_citations:,}")
        print(f"🎯 Highest citation count: {max_cites:,}")
        print(f"📊 Average citations (for cited papers): {avg_cites:.1f}")
        print()
        
        # Progress percentages
        processed_pct = (with_ss_id / total * 100) if total > 0 else 0
        cited_pct = (with_citations / total * 100) if total > 0 else 0
        
        print(f"🔄 Processing progress: {processed_pct:.2f}%")
        print(f"📈 Papers with citations: {cited_pct:.2f}%")
        print()
        
        # Top cited papers
        print("🏆 Top 10 Most Cited Papers:")
        print("-" * 40)
        
        top_papers = db.execute(text("""
            SELECT title, citation_count, arxiv_id
            FROM papers 
            WHERE is_latest_version = true 
            AND citation_count > 0
            ORDER BY citation_count DESC 
            LIMIT 10
        """)).fetchall()
        
        if top_papers:
            for i, paper in enumerate(top_papers, 1):
                title = paper.title[:60] + "..." if len(paper.title) > 60 else paper.title
                print(f"{i:2d}. {paper.citation_count:4d} citations - {title}")
        else:
            print("No papers with citations found yet.")
        
        print()
        
        # Citation distribution
        print("📊 Citation Count Distribution:")
        print("-" * 30)
        
        distribution = db.execute(text("""
            SELECT 
                CASE 
                    WHEN citation_count = 0 THEN '0 citations'
                    WHEN citation_count BETWEEN 1 AND 5 THEN '1-5 citations'
                    WHEN citation_count BETWEEN 6 AND 10 THEN '6-10 citations'
                    WHEN citation_count BETWEEN 11 AND 50 THEN '11-50 citations'
                    WHEN citation_count BETWEEN 51 AND 100 THEN '51-100 citations'
                    WHEN citation_count > 100 THEN '100+ citations'
                END as range,
                COUNT(*) as count
            FROM papers 
            WHERE is_latest_version = true 
            AND semantic_scholar_id IS NOT NULL
            GROUP BY 
                CASE 
                    WHEN citation_count = 0 THEN '0 citations'
                    WHEN citation_count BETWEEN 1 AND 5 THEN '1-5 citations'
                    WHEN citation_count BETWEEN 6 AND 10 THEN '6-10 citations'
                    WHEN citation_count BETWEEN 11 AND 50 THEN '11-50 citations'
                    WHEN citation_count BETWEEN 51 AND 100 THEN '51-100 citations'
                    WHEN citation_count > 100 THEN '100+ citations'
                END
            ORDER BY 
                CASE 
                    WHEN citation_count = 0 THEN 1
                    WHEN citation_count BETWEEN 1 AND 5 THEN 2
                    WHEN citation_count BETWEEN 6 AND 10 THEN 3
                    WHEN citation_count BETWEEN 11 AND 50 THEN 4
                    WHEN citation_count BETWEEN 51 AND 100 THEN 5
                    WHEN citation_count > 100 THEN 6
                END
        """)).fetchall()
        
        for dist in distribution:
            print(f"{dist.range:15s}: {dist.count:,} papers")
        
        print()
        
        # Recent processing activity
        print("⏰ Recent Processing Activity:")
        print("-" * 30)
        
        recent_activity = db.execute(text("""
            SELECT 
                DATE(citation_updated_at) as date,
                COUNT(*) as papers_processed
            FROM papers 
            WHERE citation_updated_at IS NOT NULL
            GROUP BY DATE(citation_updated_at)
            ORDER BY DATE(citation_updated_at) DESC
            LIMIT 7
        """)).fetchall()
        
        if recent_activity:
            for activity in recent_activity:
                print(f"{activity.date}: {activity.papers_processed:,} papers processed")
        else:
            print("No recent processing activity found.")
        
        print()
        
        # Estimation for completion
        remaining = total - with_ss_id
        if remaining > 0:
            print(f"🔮 Remaining papers to process: {remaining:,}")
            print(f"⏱️  At 1 paper/second: ~{remaining/3600:.1f} hours")
            print(f"📅 At 100 papers/batch: ~{remaining/100:.0f} batches needed")
        else:
            print("🎉 All papers have been processed!")
        
    except Exception as e:
        print(f"❌ Error checking progress: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_citation_progress()
