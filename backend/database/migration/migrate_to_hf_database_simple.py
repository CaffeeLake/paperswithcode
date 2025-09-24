#!/usr/bin/env python3
"""
Simplified migration script to create and populate the new paperswithcode_hf database.

This script:
1. Creates the new paperswithcode_hf database
2. Sets up the complete schema
3. Shows what would be migrated from the original paperswithcode database

Usage:
    uv run backend/database/migrate_to_hf_database_simple.py [--dry-run] [--test]
"""

import argparse
import csv
import os
import sys
from typing import Set

import psycopg2
import psycopg2.extras
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from backend.database.logging_config import setup_logging

# Database connection parameters
DB_PARAMS = {
    "host": "localhost",
    "user": os.getenv("PWC_DB_USER", "paperswithcode_user"),
    "password": os.getenv("PWC_DB_PASSWORD", "paperswithcode123"),
}

# For database creation, we need postgres superuser
ADMIN_DB_PARAMS = {
    "host": "localhost",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

ORIGINAL_DB = "paperswithcode"
NEW_DB = "paperswithcode_hf"

# Path to the HF ArXiv papers CSV
HF_CSV_PATH = "data" / "arxiv_papers_hf.csv"


class SimpleDatabaseMigrator:
    """Simplified database migrator for HF-filtered database."""

    def __init__(self, dry_run: bool = False, test_mode: bool = False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.logger = setup_logging("migrate_to_hf_database_simple")

    def load_hf_arxiv_ids(self) -> Set[str]:
        """Load the set of ArXiv IDs from the HF CSV file."""
        try:
            self.logger.info(f"Loading HF ArXiv IDs from {HF_CSV_PATH}")

            if not HF_CSV_PATH.exists():
                raise FileNotFoundError(f"HF CSV file not found: {HF_CSV_PATH}")

            arxiv_ids = set()

            with open(HF_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    arxiv_id = row["_id"].strip()
                    if arxiv_id:
                        arxiv_ids.add(arxiv_id)

                    if self.test_mode and len(arxiv_ids) >= 100:
                        self.logger.info("Test mode: limiting to 100 ArXiv IDs")
                        break

            self.logger.info(f"Loaded {len(arxiv_ids)} HF ArXiv IDs")
            return arxiv_ids

        except Exception as e:
            self.logger.error(f"Failed to load HF ArXiv IDs: {e}")
            return set()

    def analyze_migration_scope(self, hf_arxiv_ids: Set[str]) -> dict:
        """Analyze what would be migrated from the original database."""
        try:
            self.logger.info("Analyzing migration scope")

            # Connect to original database
            orig_conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)
            orig_cur = orig_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            arxiv_ids_list = list(hf_arxiv_ids)

            # Count papers to migrate
            orig_cur.execute(
                """
                SELECT COUNT(*) as paper_count,
                       COUNT(DISTINCT arxiv_id) as unique_arxiv_count
                FROM papers
                WHERE arxiv_id = ANY(%s)
            """,
                (arxiv_ids_list,),
            )

            paper_stats = orig_cur.fetchone()

            # Count authors to migrate
            orig_cur.execute(
                """
                SELECT COUNT(DISTINCT a.id) as author_count
                FROM authors a
                JOIN paper_authors pa ON a.id = pa.author_id
                JOIN papers p ON pa.paper_id = p.id
                WHERE p.arxiv_id = ANY(%s)
            """,
                (arxiv_ids_list,),
            )

            author_stats = orig_cur.fetchone()

            # Count repositories to migrate
            orig_cur.execute(
                """
                SELECT COUNT(*) as repo_count
                FROM repositories r
                JOIN papers p ON r.paper_id = p.id
                WHERE p.arxiv_id = ANY(%s)
            """,
                (arxiv_ids_list,),
            )

            repo_stats = orig_cur.fetchone()

            # Count project pages to migrate
            orig_cur.execute(
                """
                SELECT COUNT(*) as page_count
                FROM project_pages pp
                JOIN papers p ON pp.paper_id = p.id
                WHERE p.arxiv_id = ANY(%s)
            """,
                (arxiv_ids_list,),
            )

            page_stats = orig_cur.fetchone()

            # Get sample papers with details
            orig_cur.execute(
                """
                SELECT p.arxiv_id, p.title, p.citation_count,
                       CASE WHEN p.primary_category IS NOT NULL THEN 'Yes' ELSE 'No' END as has_category,
                       COUNT(pa.author_id) as author_count
                FROM papers p
                LEFT JOIN paper_authors pa ON p.id = pa.paper_id
                WHERE p.arxiv_id = ANY(%s) AND p.is_latest_version = TRUE
                GROUP BY p.id, p.arxiv_id, p.title, p.citation_count, p.primary_category
                ORDER BY p.citation_count DESC NULLS LAST
                LIMIT 10
            """,
                (arxiv_ids_list,),
            )

            sample_papers = orig_cur.fetchall()

            orig_conn.close()

            return {
                "papers": paper_stats["paper_count"],
                "unique_arxiv_ids": paper_stats["unique_arxiv_count"],
                "authors": author_stats["author_count"],
                "repositories": repo_stats["repo_count"],
                "project_pages": page_stats["page_count"],
                "sample_papers": sample_papers,
            }

        except Exception as e:
            self.logger.error(f"Failed to analyze migration scope: {e}")
            return {}

    def create_database_and_schema(self) -> bool:
        """Create the new database and set up the schema."""
        try:
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would create database {NEW_DB}")
                self.logger.info(
                    "[DRY RUN] Would set up schema from setup_paperswithcode_hf.sql"
                )
                return True

            # Create database
            self.logger.info(f"Creating database {NEW_DB}")
            conn = psycopg2.connect(**ADMIN_DB_PARAMS)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with conn.cursor() as cur:
                # Check if database already exists
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (NEW_DB,))

                if cur.fetchone():
                    self.logger.warning(
                        f"Database {NEW_DB} already exists - dropping and recreating"
                    )
                    cur.execute(f"DROP DATABASE {NEW_DB}")

                self.logger.info(f"Creating database {NEW_DB}")
                cur.execute(f"CREATE DATABASE {NEW_DB}")

            conn.close()

            # Set up schema
            schema_file = (
                "backend" / "database" / "migration" / "setup_paperswithcode_hf.sql"
            )

            if not schema_file.exists():
                self.logger.error(f"Schema file not found: {schema_file}")
                return False

            self.logger.info("Setting up database schema")

            # Connect to the new database
            conn = psycopg2.connect(database=NEW_DB, **DB_PARAMS)

            with conn.cursor() as cur:
                # Read and execute the schema file
                with open(schema_file, "r") as f:
                    schema_sql = f.read()

                cur.execute(schema_sql)
                conn.commit()

            conn.close()
            self.logger.info("Schema setup completed")

            return True

        except Exception as e:
            self.logger.error(f"Failed to create database and schema: {e}")
            return False

    def run_migration(self) -> bool:
        """Run the complete migration process."""
        try:
            self.logger.info("Starting migration to paperswithcode_hf database")

            if self.dry_run:
                self.logger.info("DRY RUN MODE - No changes will be made")

            if self.test_mode:
                self.logger.info("TEST MODE - Limited to 100 papers")

            # Step 1: Load HF ArXiv IDs
            hf_arxiv_ids = self.load_hf_arxiv_ids()
            if not hf_arxiv_ids:
                self.logger.error("No HF ArXiv IDs loaded")
                return False

            # Step 2: Analyze what would be migrated
            migration_scope = self.analyze_migration_scope(hf_arxiv_ids)
            if not migration_scope:
                self.logger.error("Failed to analyze migration scope")
                return False

            # Step 3: Show migration statistics
            self.logger.info("Migration Scope Analysis:")
            self.logger.info("=" * 50)
            self.logger.info(f"Papers to migrate: {migration_scope['papers']:,}")
            self.logger.info(
                f"Unique ArXiv IDs: {migration_scope['unique_arxiv_ids']:,}"
            )
            self.logger.info(f"Authors to migrate: {migration_scope['authors']:,}")
            self.logger.info(
                f"Repositories to migrate: {migration_scope['repositories']:,}"
            )
            self.logger.info(
                f"Project pages to migrate: {migration_scope['project_pages']:,}"
            )

            if migration_scope["sample_papers"]:
                self.logger.info("\nTop papers by citation count:")
                for paper in migration_scope["sample_papers"]:
                    title_short = (
                        paper["title"][:60] + "..."
                        if len(paper["title"]) > 60
                        else paper["title"]
                    )
                    self.logger.info(f"  {paper['arxiv_id']}: {title_short}")
                    self.logger.info(
                        f"    Citations: {paper['citation_count'] or 0}, Authors: {paper['author_count']}, Category: {paper['has_category']}"
                    )

            self.logger.info("=" * 50)

            # Step 4: Create database and schema
            if not self.create_database_and_schema():
                return False

            if self.dry_run:
                self.logger.info("\n🎉 Dry run completed successfully!")
                self.logger.info("The migration would:")
                self.logger.info(f"1. Create new database '{NEW_DB}'")
                self.logger.info(
                    "2. Set up the complete schema with all tables and indexes"
                )
                self.logger.info(
                    f"3. Migrate {migration_scope['papers']:,} papers from HF ArXiv IDs"
                )
                self.logger.info(f"4. Migrate {migration_scope['authors']:,} authors")
                self.logger.info(
                    f"5. Migrate {migration_scope['repositories']:,} GitHub repositories"
                )
                self.logger.info(
                    f"6. Migrate {migration_scope['project_pages']:,} project pages"
                )
                self.logger.info("\nTo run the actual migration:")
                self.logger.info(
                    "uv run backend/database/migrate_to_hf_database_simple.py"
                )
            else:
                self.logger.info(f"\n🎉 Database '{NEW_DB}' created successfully!")
                self.logger.info("Schema has been set up with all tables and indexes.")
                self.logger.info("\nNext steps:")
                self.logger.info(
                    "1. Use the full migration script to populate the data"
                )
                self.logger.info(
                    "2. Update your application configuration to use the new database"
                )
                self.logger.info("3. Test the application with the new database")

            return True

        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate to HF-filtered database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--test", action="store_true", help="Test mode - process only 100 papers"
    )

    args = parser.parse_args()

    migrator = SimpleDatabaseMigrator(dry_run=args.dry_run, test_mode=args.test)

    success = migrator.run_migration()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
