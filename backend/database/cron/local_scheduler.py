#!/usr/bin/env python3
"""
Local scheduler for ArXiv sync - runs on your development machine.
This is a simple alternative to CRON that works with your local database.
"""

import os
import sys
import time
import logging
import schedule
from datetime import datetime, date
from typing import Optional

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.cron.arxiv_sync import ArXivSyncer
from database.db_connection import DatabaseConfig


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('local_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LocalArXivScheduler:
    """Local scheduler for ArXiv synchronization."""
    
    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or DatabaseConfig()
        self.syncer = ArXivSyncer(self.db_config)
        
    def run_sync(self):
        """Run a single sync operation."""
        try:
            logger.info("🚀 Starting scheduled ArXiv sync...")
            
            # Test database connection first
            if not self.syncer.db.test_connection():
                logger.error("❌ Database connection failed - skipping sync")
                return
            
            # Run the sync
            results = self.syncer.sync_papers()
            
            logger.info(f"✅ Sync completed successfully: {results}")
            
            # Log summary
            if results['inserted'] > 0:
                logger.info(f"📄 Added {results['inserted']} new papers to database")
            else:
                logger.info("📄 No new papers found")
                
        except Exception as e:
            logger.error(f"❌ Sync failed: {e}")
    
    def start_scheduler(self, sync_time: str = "06:00"):
        """Start the scheduler with daily sync at specified time."""
        logger.info(f"🕐 Scheduling daily ArXiv sync at {sync_time}")
        logger.info(f"🔗 Database: {self.db_config.connection_string}")
        
        # Schedule daily sync
        schedule.every().day.at(sync_time).do(self.run_sync)
        
        # Also allow manual trigger by creating a trigger file
        trigger_file = "trigger_sync.txt"
        if os.path.exists(trigger_file):
            os.remove(trigger_file)
        
        logger.info(f"📋 Scheduler started. Next sync: {schedule.next_run()}")
        logger.info(f"💡 To trigger manual sync, create file: {trigger_file}")
        logger.info("🛑 Press Ctrl+C to stop")
        
        try:
            while True:
                # Check for manual trigger
                if os.path.exists(trigger_file):
                    logger.info("🔄 Manual sync triggered!")
                    os.remove(trigger_file)
                    self.run_sync()
                
                # Run scheduled jobs
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("🛑 Scheduler stopped by user")
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Local ArXiv sync scheduler")
    parser.add_argument("--time", default="06:00", help="Daily sync time (HH:MM format)")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--database", default="paperswithcode", help="Database name")
    parser.add_argument("--user", help="Database user")
    parser.add_argument("--password", help="Database password")
    parser.add_argument("--run-once", action="store_true", help="Run sync once and exit")
    
    args = parser.parse_args()
    
    # Create database config
    db_config = DatabaseConfig(
        host=args.host,
        database=args.database,
        user=args.user,
        password=args.password
    )
    
    scheduler = LocalArXivScheduler(db_config)
    
    if args.run_once:
        logger.info("🔄 Running one-time sync...")
        scheduler.run_sync()
    else:
        scheduler.start_scheduler(args.time)


if __name__ == "__main__":
    main()
