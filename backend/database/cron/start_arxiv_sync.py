#!/usr/bin/env python3
"""
Simple startup script for local ArXiv synchronization.
Run this to start the daily ArXiv sync scheduler on your local machine.
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent
sys.path.append(str(backend_path))

from database.cron.local_scheduler import LocalArXivScheduler
from database.db_connection import DatabaseConfig


def main():
    print("🚀 PapersWithCode - Local ArXiv Sync Scheduler")
    print("=" * 50)
    
    # Use default local database configuration
    db_config = DatabaseConfig()
    
    print(f"📊 Database: {db_config.database}")
    print(f"🔗 Host: {db_config.host}:{db_config.port}")
    print(f"👤 User: {db_config.user}")
    print()
    
    # Test database connection
    scheduler = LocalArXivScheduler(db_config)
    
    print("🔌 Testing database connection...")
    if not scheduler.syncer.db.test_connection():
        print("❌ Database connection failed!")
        print("💡 Make sure PostgreSQL is running and the database exists.")
        print("💡 Run: brew services start postgresql@15")
        return 1
    
    print("✅ Database connection successful!")
    
    # Get current paper count
    paper_count = scheduler.syncer.db.get_paper_count()
    latest_date = scheduler.syncer.db.get_latest_paper_date()
    
    print(f"📄 Current papers in database: {paper_count:,}")
    print(f"📅 Latest paper date: {latest_date}")
    print()
    
    # Ask user what they want to do
    print("What would you like to do?")
    print("1. Start daily scheduler (runs at 6:00 AM)")
    print("2. Run sync once now")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        print("\n🕐 Starting daily scheduler...")
        print("💡 To manually trigger sync, create file: backend/database/trigger_sync.txt")
        print("🛑 Press Ctrl+C to stop")
        scheduler.start_scheduler()
    
    elif choice == "2":
        print("\n🔄 Running sync now...")
        scheduler.run_sync()
        print("✅ Sync completed!")
    
    elif choice == "3":
        print("👋 Goodbye!")
        return 0
    
    else:
        print("❌ Invalid choice")
        return 1


if __name__ == "__main__":
    sys.exit(main())
