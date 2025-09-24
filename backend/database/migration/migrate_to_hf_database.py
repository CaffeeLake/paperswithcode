#!/usr/bin/env python3
"""
Migration script to create and populate the new paperswithcode_hf database.

This script:
1. Creates the new paperswithcode_hf database
2. Sets up the complete schema
3. Migrates relevant data from the original paperswithcode database
4. Populates with HF ArXiv papers from the CSV file

Usage:
    uv run backend/database/migrate_to_hf_database.py [--dry-run] [--test]
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


class DatabaseMigrator:
    """Handles migration from original database to HF-filtered database."""

    def __init__(self, dry_run: bool = False, test_mode: bool = False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.logger = setup_logging("migrate_to_hf_database")

        # Statistics tracking
        self.stats = {
            "hf_papers_found": 0,
            "papers_migrated": 0,
            "authors_migrated": 0,
            "repositories_migrated": 0,
            "project_pages_migrated": 0,
            "citations_migrated": 0,
        }

    def create_database(self) -> bool:
        """Create the new paperswithcode_hf database."""
        try:
            # Connect to PostgreSQL without specifying a database (use admin credentials)
            conn = psycopg2.connect(**ADMIN_DB_PARAMS)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with conn.cursor() as cur:
                # Check if database already exists
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (NEW_DB,))

                if cur.fetchone():
                    self.logger.warning(f"Database {NEW_DB} already exists")
                    if not self.dry_run:
                        response = input(f"Drop and recreate {NEW_DB}? [y/N]: ")
                        if response.lower() != "y":
                            self.logger.info("Aborted by user")
                            return False

                        self.logger.info(f"Dropping existing database {NEW_DB}")
                        cur.execute(f"DROP DATABASE {NEW_DB}")

                if not self.dry_run:
                    self.logger.info(f"Creating database {NEW_DB}")
                    cur.execute(f"CREATE DATABASE {NEW_DB}")
                else:
                    self.logger.info(f"[DRY RUN] Would create database {NEW_DB}")

            conn.close()
            return True

        except Exception as e:
            self.logger.error(f"Failed to create database: {e}")
            return False

    def setup_schema(self) -> bool:
        """Set up the complete schema in the new database."""
        try:
            schema_file = "backend" / "database" / "setup_paperswithcode_hf.sql"

            if not schema_file.exists():
                self.logger.error(f"Schema file not found: {schema_file}")
                return False

            if not self.dry_run:
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
            else:
                self.logger.info(f"[DRY RUN] Would execute schema from {schema_file}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to setup schema: {e}")
            return False

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

            self.stats["hf_papers_found"] = len(arxiv_ids)
            self.logger.info(f"Loaded {len(arxiv_ids)} HF ArXiv IDs")

            return arxiv_ids

        except Exception as e:
            self.logger.error(f"Failed to load HF ArXiv IDs: {e}")
            return set()

    def migrate_papers_and_authors(self, hf_arxiv_ids: Set[str]) -> bool:
        """Migrate papers and authors from original database."""
        try:
            self.logger.info("Migrating papers and authors")

            # Connect to original database
            orig_conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)

            if not self.dry_run:
                # Connect to new database only if not in dry-run mode
                new_conn = psycopg2.connect(database=NEW_DB, **DB_PARAMS)
                new_cur = new_conn.cursor()
            else:
                new_conn = None
                new_cur = None

            orig_cur = orig_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Create mapping from old paper IDs to new paper IDs
            paper_id_mapping = {}
            author_id_mapping = {}

            # Get papers that match HF ArXiv IDs
            arxiv_ids_tuple = tuple(hf_arxiv_ids)

            self.logger.info(
                f"Querying papers from original database (matching {len(arxiv_ids_tuple)} HF ArXiv IDs)"
            )

            orig_cur.execute(
                """
                SELECT id, title, abstract, arxiv_id, version, is_latest_version,
                       date_published, proceeding, conference, conference_url_abs, conference_url_pdf,
                       citation_count, semantic_scholar_id, citation_updated_at,
                       primary_category, all_categories,
                       created_at, updated_at
                FROM papers
                WHERE arxiv_id = ANY(%s)
                ORDER BY arxiv_id, version
            """,
                (arxiv_ids_tuple,),
            )

            papers = orig_cur.fetchall()
            self.logger.info(f"Found {len(papers)} papers to migrate")

            if not self.dry_run:
                # Migrate papers
                for paper in papers:
                    new_cur.execute(
                        """
                        INSERT INTO papers (
                            title, abstract, arxiv_id, version, is_latest_version,
                            date_published, proceeding, conference, conference_url_abs, conference_url_pdf,
                            citation_count, semantic_scholar_id, citation_updated_at,
                            primary_category, all_categories,
                            created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) RETURNING id
                    """,
                        (
                            paper["title"],
                            paper["abstract"],
                            paper["arxiv_id"],
                            paper["version"],
                            paper["is_latest_version"],
                            paper["date_published"],
                            paper["proceeding"],
                            paper["conference"],
                            paper["conference_url_abs"],
                            paper["conference_url_pdf"],
                            paper["citation_count"],
                            paper["semantic_scholar_id"],
                            paper["citation_updated_at"],
                            paper["primary_category"],
                            paper["all_categories"],
                            paper["created_at"],
                            paper["updated_at"],
                        ),
                    )

                    new_paper_id = new_cur.fetchone()[0]
                    paper_id_mapping[paper["id"]] = new_paper_id

                self.stats["papers_migrated"] = len(papers)
                self.logger.info(f"Migrated {len(papers)} papers")

                # Get all authors for these papers
                paper_ids_tuple = tuple(paper["id"] for paper in papers)

                orig_cur.execute(
                    """
                    SELECT DISTINCT a.id, a.name, a.hf_username, a.hf_id, a.hf_avatar_url,
                           a.hf_status, a.hf_is_pro, a.created_at, a.updated_at
                    FROM authors a
                    JOIN paper_authors pa ON a.id = pa.author_id
                    WHERE pa.paper_id = ANY(%s)
                """,
                    (paper_ids_tuple,),
                )

                authors = orig_cur.fetchall()
                self.logger.info(f"Found {len(authors)} authors to migrate")

                # Migrate authors
                for author in authors:
                    new_cur.execute(
                        """
                        INSERT INTO authors (
                            name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """,
                        (
                            author["name"],
                            author["hf_username"],
                            author["hf_id"],
                            author["hf_avatar_url"],
                            author["hf_status"],
                            author["hf_is_pro"],
                            author["created_at"],
                            author["updated_at"],
                        ),
                    )

                    new_author_id = new_cur.fetchone()[0]
                    author_id_mapping[author["id"]] = new_author_id

                self.stats["authors_migrated"] = len(authors)
                self.logger.info(f"Migrated {len(authors)} authors")

                # Migrate paper-author relationships
                orig_cur.execute(
                    """
                    SELECT paper_id, author_id, author_order
                    FROM paper_authors
                    WHERE paper_id = ANY(%s)
                """,
                    (paper_ids_tuple,),
                )

                paper_authors = orig_cur.fetchall()

                for pa in paper_authors:
                    if (
                        pa["paper_id"] in paper_id_mapping
                        and pa["author_id"] in author_id_mapping
                    ):
                        new_cur.execute(
                            """
                            INSERT INTO paper_authors (paper_id, author_id, author_order)
                            VALUES (%s, %s, %s)
                        """,
                            (
                                paper_id_mapping[pa["paper_id"]],
                                author_id_mapping[pa["author_id"]],
                                pa["author_order"],
                            ),
                        )

                self.logger.info(
                    f"Migrated {len(paper_authors)} paper-author relationships"
                )

                new_conn.commit()
            else:
                self.logger.info(
                    f"[DRY RUN] Would migrate {len(papers)} papers and their authors"
                )

            orig_conn.close()
            if new_conn:
                new_conn.close()

            return True

        except Exception as e:
            self.logger.error(f"Failed to migrate papers and authors: {e}")
            return False

    def migrate_repositories_and_pages(self, hf_arxiv_ids: Set[str]) -> bool:
        """Migrate repositories and project pages for HF papers."""
        try:
            self.logger.info("Migrating repositories and project pages")

            # Connect to both databases
            orig_conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)
            new_conn = psycopg2.connect(database=NEW_DB, **DB_PARAMS)

            orig_cur = orig_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            new_cur = new_conn.cursor()

            # Get paper ID mappings
            arxiv_ids_tuple = tuple(hf_arxiv_ids)

            # Create mapping from old paper IDs to new paper IDs
            orig_cur.execute(
                """
                SELECT id, arxiv_id FROM papers WHERE arxiv_id = ANY(%s)
            """,
                (arxiv_ids_tuple,),
            )
            orig_papers = {row["id"]: row["arxiv_id"] for row in orig_cur.fetchall()}

            new_cur.execute(
                """
                SELECT id, arxiv_id FROM papers WHERE arxiv_id = ANY(%s)
            """,
                (arxiv_ids_tuple,),
            )
            new_papers = {row["arxiv_id"]: row["id"] for row in new_cur.fetchall()}

            paper_id_mapping = {}
            for orig_id, arxiv_id in orig_papers.items():
                if arxiv_id in new_papers:
                    paper_id_mapping[orig_id] = new_papers[arxiv_id]

            if not self.dry_run:
                # Migrate repositories
                orig_paper_ids = tuple(paper_id_mapping.keys())

                orig_cur.execute(
                    """
                    SELECT paper_id, url, owner, name, num_stars, is_official, source,
                           created_at, updated_at
                    FROM repositories
                    WHERE paper_id = ANY(%s)
                """,
                    (orig_paper_ids,),
                )

                repositories = orig_cur.fetchall()

                for repo in repositories:
                    if repo["paper_id"] in paper_id_mapping:
                        new_cur.execute(
                            """
                            INSERT INTO repositories (
                                paper_id, url, owner, name, num_stars, is_official, source,
                                created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                            (
                                paper_id_mapping[repo["paper_id"]],
                                repo["url"],
                                repo["owner"],
                                repo["name"],
                                repo["num_stars"],
                                repo["is_official"],
                                repo["source"],
                                repo["created_at"],
                                repo["updated_at"],
                            ),
                        )

                self.stats["repositories_migrated"] = len(repositories)
                self.logger.info(f"Migrated {len(repositories)} repositories")

                # Migrate project pages
                orig_cur.execute(
                    """
                    SELECT paper_id, url, is_official, source, created_at, updated_at
                    FROM project_pages
                    WHERE paper_id = ANY(%s)
                """,
                    (orig_paper_ids,),
                )

                project_pages = orig_cur.fetchall()

                for page in project_pages:
                    if page["paper_id"] in paper_id_mapping:
                        new_cur.execute(
                            """
                            INSERT INTO project_pages (
                                paper_id, url, is_official, source, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                            (
                                paper_id_mapping[page["paper_id"]],
                                page["url"],
                                page["is_official"],
                                page["source"],
                                page["created_at"],
                                page["updated_at"],
                            ),
                        )

                self.stats["project_pages_migrated"] = len(project_pages)
                self.logger.info(f"Migrated {len(project_pages)} project pages")

                new_conn.commit()
            else:
                self.logger.info(
                    "[DRY RUN] Would migrate repositories and project pages"
                )

            orig_conn.close()
            new_conn.close()

            return True

        except Exception as e:
            self.logger.error(f"Failed to migrate repositories and pages: {e}")
            return False

    def print_statistics(self):
        """Print migration statistics."""
        self.logger.info("Migration Statistics:")
        self.logger.info("=" * 50)
        for key, value in self.stats.items():
            self.logger.info(f"{key.replace('_', ' ').title()}: {value:,}")
        self.logger.info("=" * 50)

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

            # Step 2: Create new database
            if not self.create_database():
                return False

            # Step 3: Setup schema
            if not self.setup_schema():
                return False

            # Step 4: Migrate papers and authors
            if not self.migrate_papers_and_authors(hf_arxiv_ids):
                return False

            # Step 5: Migrate repositories and project pages
            if not self.migrate_repositories_and_pages(hf_arxiv_ids):
                return False

            # Print final statistics
            self.print_statistics()

            self.logger.info("Migration completed successfully!")

            if not self.dry_run:
                self.logger.info(f"New database '{NEW_DB}' is ready to use")
                self.logger.info("Next steps:")
                self.logger.info(
                    "1. Update your application configuration to use the new database"
                )
                self.logger.info("2. Test the application with the new database")
                self.logger.info(
                    "3. Consider backing up the original database before switching"
                )

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

    migrator = DatabaseMigrator(dry_run=args.dry_run, test_mode=args.test)

    success = migrator.run_migration()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
