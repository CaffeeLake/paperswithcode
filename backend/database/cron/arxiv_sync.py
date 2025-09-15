"""
This script fetches new papers from the ArXiv API and updates the database daily.

It can be run manually or as a cron job. Manually like so:

```bash
uv run backend/database/cron/arxiv_sync.py
```
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import requests
import xml.etree.ElementTree as ET
import argparse
import re

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_connection import PapersDatabase, DatabaseConfig


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arxiv_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ArXivSyncer:
    """ArXiv API synchronization manager."""
    
    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db = PapersDatabase(db_config)
        
        # ArXiv API settings
        self.arxiv_base_url = "http://export.arxiv.org/api/query"
        self.batch_size = 100  # ArXiv API limit
        self.delay_between_requests = 3  # Seconds (ArXiv rate limiting)
        
        # Computer Science categories (focus on AI/ML)
        self.cs_categories = [
            'cs.AI',  # Artificial Intelligence
            'cs.LG',  # Machine Learning
            'cs.CV',  # Computer Vision
            'cs.CL',  # Computation and Language (NLP)
            'cs.NE',  # Neural and Evolutionary Computing
            'cs.RO',  # Robotics
            'cs.IR',  # Information Retrieval
            'stat.ML'  # Statistics - Machine Learning
        ]

    def get_last_sync_date(self) -> date:
        """Get the date of the most recent paper in the database."""
        try:
            last_date = self.db.get_latest_paper_date()
            if last_date:
                logger.info(f"Last sync date: {last_date}")
                return last_date
            else:
                # Fallback to known data end
                fallback_date = date(2025, 9, 4)
                logger.info(f"No papers found, using fallback date: {fallback_date}")
                return fallback_date
        except Exception as e:
            logger.error(f"Error getting last sync date: {e}")
            return date(2025, 9, 4)  # Fallback

    def build_arxiv_query(self, start_date: date, end_date: date, start_index: int = 0) -> str:
        """Build ArXiv API query URL."""
        # Format dates for ArXiv API (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        # Build category filter
        category_filter = " OR ".join([f"cat:{cat}" for cat in self.cs_categories])
        
        # Build date range filter
        date_filter = f"submittedDate:[{start_str}0000 TO {end_str}2359]"
        
        # Combine filters
        search_query = f"({category_filter}) AND {date_filter}"
        
        params = {
            'search_query': search_query,
            'start': start_index,
            'max_results': self.batch_size,
            'sortBy': 'submittedDate',
            'sortOrder': 'ascending'
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.arxiv_base_url}?{query_string}"

    def parse_arxiv_entry(self, entry: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single ArXiv entry from XML."""
        try:
            # Namespaces
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
            
            # Extract ArXiv ID and version
            arxiv_id_full = entry.find('atom:id', ns).text.split('/')[-1]
            arxiv_match = re.match(r'(\d+\.\d+)(v\d+)?', arxiv_id_full)
            if not arxiv_match:
                logger.warning(f"Could not parse ArXiv ID: {arxiv_id_full}")
                return None
            
            arxiv_id = arxiv_match.group(1)
            version = arxiv_match.group(2) or 'v1'
            
            # Extract basic info
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            
            # Extract publication date
            published = entry.find('atom:published', ns).text
            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00')).date()
            
            # Extract categories
            categories = [cat.get('term') for cat in entry.findall('atom:category', ns)]
            primary_category = categories[0] if categories else None
            
            # Extract authors
            authors = []
            for author in entry.findall('atom:author', ns):
                name = author.find('atom:name', ns).text
                authors.append(name)
            
            return {
                'arxiv_id': arxiv_id,
                'version': version,
                'title': title,
                'abstract': summary,
                'date_published': pub_date,
                'is_latest_version': True,  # Assume latest version for now
                'proceeding': None,
                'conference': None,
                'conference_url_abs': None,
                'conference_url_pdf': None,
                'primary_category': primary_category,
                'all_categories': categories,
                'authors': authors
            }
            
        except Exception as e:
            logger.error(f"Error parsing ArXiv entry: {e}")
            return None

    def fetch_arxiv_papers(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Fetch papers from ArXiv API for the given date range."""
        papers = []
        start_index = 0
        
        logger.info(f"Fetching papers from {start_date} to {end_date}")
        
        while True:
            url = self.build_arxiv_query(start_date, end_date, start_index)
            logger.info(f"Fetching batch starting at index {start_index}")
            
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Parse XML
                root = ET.fromstring(response.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)
                
                if not entries:
                    logger.info("No more entries found")
                    break
                
                batch_papers = []
                for entry in entries:
                    paper_data = self.parse_arxiv_entry(entry)
                    if paper_data:
                        batch_papers.append(paper_data)
                
                papers.extend(batch_papers)
                logger.info(f"Parsed {len(batch_papers)} papers in this batch")
                
                # Check if we got fewer results than requested (last page)
                if len(entries) < self.batch_size:
                    break
                
                start_index += self.batch_size
                
                # Rate limiting
                time.sleep(self.delay_between_requests)
                
            except requests.RequestException as e:
                logger.error(f"Error fetching from ArXiv API: {e}")
                break
            except ET.ParseError as e:
                logger.error(f"Error parsing XML response: {e}")
                break
        
        logger.info(f"Total papers fetched: {len(papers)}")
        return papers

    def sync_papers(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, int]:
        """Main sync function."""
        try:
            # Test database connection
            if not self.db.test_connection():
                raise Exception("Database connection failed")
            
            # Determine date range
            if not start_date:
                start_date = self.get_last_sync_date() + timedelta(days=1)
            
            if not end_date:
                end_date = date.today()
            
            if start_date > end_date:
                logger.info("No new papers to sync")
                return {'fetched': 0, 'inserted': 0, 'skipped': 0}
            
            # Split large date ranges into smaller chunks (30 days max)
            total_results = {'fetched': 0, 'inserted': 0, 'skipped': 0}
            current_start = start_date
            
            while current_start <= end_date:
                # Calculate chunk end date (30 days or end_date, whichever is smaller)
                chunk_end = min(current_start + timedelta(days=29), end_date)
                
                logger.info(f"Processing chunk: {current_start} to {chunk_end}")
                
                # Fetch papers for this chunk
                papers = self.fetch_arxiv_papers(current_start, chunk_end)
                total_results['fetched'] += len(papers)
                
                # Insert papers into database
                for paper in papers:
                    if self.db.paper_exists(paper['arxiv_id'], paper['version']):
                        total_results['skipped'] += 1
                        continue
                    
                    paper_id = self.db.insert_paper(paper)
                    if paper_id:
                        total_results['inserted'] += 1
                        if total_results['inserted'] % 50 == 0:
                            logger.info(f"Inserted {total_results['inserted']} papers so far...")
                    else:
                        total_results['skipped'] += 1
                
                # Move to next chunk
                current_start = chunk_end + timedelta(days=1)
                
                # Add a small delay between chunks to be respectful to ArXiv API
                if current_start <= end_date:
                    time.sleep(2)
            
            logger.info(f"Sync completed: {total_results}")
            return total_results
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            raise
        finally:
            self.db.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Sync ArXiv papers to PostgreSQL database")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--database", default="paperswithcode", help="Database name")
    parser.add_argument("--user", help="Database user")
    parser.add_argument("--password", help="Database password")
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = None
    end_date = None
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    
    # Create database config
    db_config = DatabaseConfig(
        host=args.host,
        database=args.database,
        user=args.user,
        password=args.password
    )
    
    # Create syncer and run
    syncer = ArXivSyncer(db_config)
    
    try:
        results = syncer.sync_papers(start_date, end_date)
        logger.info(f"Final results: {results}")
        
        # Exit with error code if no papers were processed
        if results['fetched'] == 0 and start_date and start_date < date.today():
            logger.warning("No papers fetched - this might indicate an issue")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()