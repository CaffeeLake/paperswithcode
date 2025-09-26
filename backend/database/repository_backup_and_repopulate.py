#!/usr/bin/env python3
"""
Repository Backup and Repopulation Script

This script:
1. Creates a RepositoryBackup table and copies existing Repository data
2. Clears all data from the Repository table
3. Populates Repository table with data from links-between-papers-and-code.json

Usage:
    uv run backend/database/repository_backup_and_repopulate.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))


# Load environment variables from keys.env
def load_env_file(env_file_path: str):
    """Load environment variables from a .env file."""
    if not os.path.exists(env_file_path):
        print(f"❌ Environment file not found: {env_file_path}")
        return

    with open(env_file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value


# Load environment variables
env_file = Path(__file__).parent.parent / "keys.env"
load_env_file(str(env_file))

# Database connection parameters from environment
DB_PARAMS = {
    "host": os.getenv("PWC_DB_HOST", "localhost"),
    "port": int(os.getenv("PWC_DB_PORT", "5432")),
    "user": os.getenv("PWC_DB_USER", "paperswithcode_user"),
    "password": os.getenv("PWC_DB_PASSWORD", "paperswithcode123"),
    "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
}

# Path to the JSON file
JSON_FILE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "links-between-papers-and-code.json"
)


class RepositoryManager:
    """Handles repository backup, clearing, and repopulation."""

    def __init__(self):
        self.db_params = DB_PARAMS
        print(f"🔗 Connecting to database: {self.db_params['database']}")

    def get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(**self.db_params)

    def backup_repository_table(self):
        """Create RepositoryBackup table and copy existing Repository data."""
        print("\n📋 Step 1: Creating RepositoryBackup table and copying data...")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Drop existing backup table if it exists
                cur.execute("DROP TABLE IF EXISTS repositorybackup CASCADE;")

                # Create backup table with same structure as repositories
                cur.execute("""
                    CREATE TABLE repositorybackup AS
                    SELECT * FROM repositories;
                """)

                # Add primary key and indexes to backup table
                cur.execute("""
                    ALTER TABLE repositorybackup
                    ADD COLUMN backup_id BIGSERIAL PRIMARY KEY;
                """)

                cur.execute("""
                    CREATE INDEX idx_repositorybackup_paper_id ON repositorybackup(paper_id);
                    CREATE INDEX idx_repositorybackup_url ON repositorybackup(url);
                """)

                # Get count of backed up records
                cur.execute("SELECT COUNT(*) FROM repositorybackup;")
                backup_count = cur.fetchone()[0]

                conn.commit()
                print(
                    f"✅ Backed up {backup_count:,} repository records to RepositoryBackup table"
                )

    def clear_repository_table(self):
        """Clear all data from Repository table."""
        print("\n🗑️  Step 2: Clearing Repository table...")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Get count before clearing
                cur.execute("SELECT COUNT(*) FROM repositories;")
                before_count = cur.fetchone()[0]

                # Clear the table (using DELETE instead of TRUNCATE to avoid sequence ownership issues)
                cur.execute("DELETE FROM repositories;")

                conn.commit()
                print(f"✅ Cleared {before_count:,} records from Repository table")

    def extract_github_info(self, repo_url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract owner and name from GitHub URL."""
        try:
            parsed = urlparse(repo_url)
            if parsed.netloc.lower() in ["github.com", "www.github.com"]:
                path_parts = [p for p in parsed.path.split("/") if p]
                if len(path_parts) >= 2:
                    return path_parts[0], path_parts[1]
        except Exception:
            pass
        return None, None

    def get_paper_id_mapping(self) -> Dict[str, int]:
        """Create a mapping from arxiv_id to paper_id."""
        print("📊 Creating paper ID mapping...")

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, arxiv_id
                    FROM papers
                    WHERE arxiv_id IS NOT NULL AND arxiv_id != ''
                """)

                mapping = {}
                for row in cur.fetchall():
                    # Handle different arxiv_id formats
                    arxiv_id = row["arxiv_id"].strip()
                    if arxiv_id:
                        # Store both with and without version numbers
                        mapping[arxiv_id] = row["id"]
                        # Also store without version (e.g., "1601.02063" from "1601.02063v2")
                        if "v" in arxiv_id:
                            base_id = arxiv_id.split("v")[0]
                            mapping[base_id] = row["id"]

                print(f"📊 Created mapping for {len(mapping):,} arxiv IDs")
                return mapping

    def populate_from_json(self):
        """Populate Repository table with data from JSON file."""
        print(f"\n📥 Step 3: Populating Repository table from {JSON_FILE_PATH.name}...")

        if not JSON_FILE_PATH.exists():
            print(f"❌ JSON file not found: {JSON_FILE_PATH}")
            return

        # Get paper ID mapping
        paper_id_mapping = self.get_paper_id_mapping()

        # Load and process JSON data
        print("📖 Loading JSON data...")
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"📊 Loaded {len(data):,} repository links from JSON")

        # Process data in batches
        batch_size = 1000
        total_inserted = 0
        total_skipped = 0

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                batch = []

                for i, item in enumerate(data):
                    # Extract arxiv_id
                    arxiv_id = item.get("paper_arxiv_id")
                    if not arxiv_id:
                        total_skipped += 1
                        continue

                    # Find corresponding paper_id
                    paper_id = paper_id_mapping.get(arxiv_id)
                    if not paper_id:
                        # Try without version number
                        if "v" in arxiv_id:
                            base_arxiv_id = arxiv_id.split("v")[0]
                            paper_id = paper_id_mapping.get(base_arxiv_id)

                    if not paper_id:
                        total_skipped += 1
                        continue

                    # Extract GitHub info
                    repo_url = item.get("repo_url", "").strip()
                    if not repo_url:
                        total_skipped += 1
                        continue

                    owner, name = self.extract_github_info(repo_url)

                    # Prepare record for insertion
                    record = (
                        paper_id,
                        repo_url,
                        owner,
                        name,
                        0,  # num_stars (default)
                        item.get("is_official", False),
                        "links_json",  # source
                    )

                    batch.append(record)

                    # Insert batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        self._insert_batch(cur, batch)
                        total_inserted += len(batch)
                        batch = []

                        if (i + 1) % 10000 == 0:
                            print(
                                f"📊 Processed {i + 1:,} records, inserted {total_inserted:,}, skipped {total_skipped:,}"
                            )

                # Insert remaining records
                if batch:
                    self._insert_batch(cur, batch)
                    total_inserted += len(batch)

                conn.commit()

        print(f"✅ Successfully inserted {total_inserted:,} repository records")
        print(
            f"⚠️  Skipped {total_skipped:,} records (no matching paper or missing data)"
        )

    def _insert_batch(self, cursor, batch: List[tuple]):
        """Insert a batch of repository records."""
        insert_query = """
            INSERT INTO repositories (
                paper_id, url, owner, name, num_stars, is_official, source
            ) VALUES %s
            ON CONFLICT (paper_id, url) DO UPDATE SET
                owner = EXCLUDED.owner,
                name = EXCLUDED.name,
                is_official = EXCLUDED.is_official,
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP
        """

        try:
            psycopg2.extras.execute_values(
                cursor, insert_query, batch, template=None, page_size=100
            )
        except Exception as e:
            print(f"❌ Error inserting batch: {e}")
            # Try inserting records one by one to identify problematic records
            for record in batch:
                try:
                    cursor.execute(
                        """
                        INSERT INTO repositories (
                            paper_id, url, owner, name, num_stars, is_official, source
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (paper_id, url) DO UPDATE SET
                            owner = EXCLUDED.owner,
                            name = EXCLUDED.name,
                            is_official = EXCLUDED.is_official,
                            source = EXCLUDED.source,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        record,
                    )
                except Exception as record_error:
                    print(f"❌ Error with record {record}: {record_error}")

    def verify_results(self):
        """Verify the results of the operation."""
        print("\n🔍 Verification:")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Check backup table
                cur.execute("SELECT COUNT(*) FROM repositorybackup;")
                backup_count = cur.fetchone()[0]

                # Check current repositories table
                cur.execute("SELECT COUNT(*) FROM repositories;")
                current_count = cur.fetchone()[0]

                # Check source distribution
                cur.execute("""
                    SELECT source, COUNT(*)
                    FROM repositories
                    GROUP BY source
                    ORDER BY COUNT(*) DESC;
                """)
                source_stats = cur.fetchall()

                print(f"📊 RepositoryBackup table: {backup_count:,} records")
                print(f"📊 Current Repository table: {current_count:,} records")
                print("\n📊 Source distribution:")
                for source, count in source_stats:
                    print(f"   {source}: {count:,} records")

    def run(self):
        """Run the complete backup, clear, and repopulate process."""
        print("🚀 Starting Repository Backup and Repopulation Process")
        print(f"📁 Using database: {self.db_params['database']}")
        print(f"📁 JSON file: {JSON_FILE_PATH}")

        try:
            # Step 1: Backup existing data
            self.backup_repository_table()

            # Step 2: Clear repository table
            self.clear_repository_table()

            # Step 3: Populate from JSON
            self.populate_from_json()

            # Step 4: Verify results
            self.verify_results()

            print("\n🎉 Repository backup and repopulation completed successfully!")

        except Exception as e:
            print(f"\n❌ Error during process: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


def main():
    """Main function."""
    manager = RepositoryManager()
    manager.run()


if __name__ == "__main__":
    main()
