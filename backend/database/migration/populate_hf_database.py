#!/usr/bin/env python3
"""
Direct data migration script to populate paperswithcode_hf database.

This script directly migrates data from the original paperswithcode database
to the new paperswithcode_hf database using SQL queries.
"""

import csv
import logging
import os
import sys
from typing import Set

import psycopg2
import psycopg2.extras

from backend.database.logging_config import setup_logging

# Database connection parameters
DB_PARAMS = {
    "host": "localhost",
    "user": os.getenv("PWC_DB_USER", "paperswithcode_user"),
    "password": os.getenv("PWC_DB_PASSWORD", "paperswithcode123"),
}

ORIGINAL_DB = "paperswithcode"
NEW_DB = "paperswithcode_hf"

# Path to the HF ArXiv papers CSV
HF_CSV_PATH = "data" / "arxiv_papers_hf.csv"


def load_hf_arxiv_ids() -> Set[str]:
    """Load the set of ArXiv IDs from the HF CSV file."""
    logger = logging.getLogger(__name__)
    logger.info(f"Loading HF ArXiv IDs from {HF_CSV_PATH}")

    if not HF_CSV_PATH.exists():
        raise FileNotFoundError(f"HF CSV file not found: {HF_CSV_PATH}")

    arxiv_ids = set()

    with open(HF_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            arxiv_id = row["_id"].strip()
            if arxiv_id:
                arxiv_ids.add(arxiv_id)

    logger.info(f"Loaded {len(arxiv_ids)} HF ArXiv IDs")
    return arxiv_ids


def migrate_papers_and_authors(hf_arxiv_ids: Set[str]):
    """Migrate papers and authors from original database."""
    logger = logging.getLogger(__name__)
    logger.info("Migrating papers and authors")

    # Connect to both databases
    orig_conn = psycopg2.connect(database=ORIGINAL_DB, **DB_PARAMS)
    new_conn = psycopg2.connect(database=NEW_DB, **DB_PARAMS)

    try:
        orig_cur = orig_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        new_cur = new_conn.cursor()

        arxiv_ids_list = list(hf_arxiv_ids)

        # Migrate papers
        logger.info("Migrating papers...")
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
            (arxiv_ids_list,),
        )

        papers = orig_cur.fetchall()
        logger.info(f"Found {len(papers)} papers to migrate")

        # Create mapping from old paper IDs to new paper IDs
        paper_id_mapping = {}

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

        logger.info(f"Migrated {len(papers)} papers")

        # Get all authors for these papers
        paper_ids_list = list(paper["id"] for paper in papers)

        logger.info("Migrating authors...")
        orig_cur.execute(
            """
            SELECT DISTINCT a.id, a.name, a.hf_username, a.hf_id, a.hf_avatar_url,
                   a.hf_status, a.hf_is_pro, a.created_at, a.updated_at
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            WHERE pa.paper_id = ANY(%s)
        """,
            (paper_ids_list,),
        )

        authors = orig_cur.fetchall()
        logger.info(f"Found {len(authors)} authors to migrate")

        # Create mapping from old author IDs to new author IDs
        author_id_mapping = {}

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

        logger.info(f"Migrated {len(authors)} authors")

        # Migrate paper-author relationships
        logger.info("Migrating paper-author relationships...")
        orig_cur.execute(
            """
            SELECT paper_id, author_id, author_order
            FROM paper_authors
            WHERE paper_id = ANY(%s)
        """,
            (paper_ids_list,),
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

        logger.info(f"Migrated {len(paper_authors)} paper-author relationships")

        # Migrate repositories
        logger.info("Migrating repositories...")
        orig_cur.execute(
            """
            SELECT paper_id, url, owner, name, num_stars, is_official, source,
                   created_at, updated_at
            FROM repositories
            WHERE paper_id = ANY(%s)
        """,
            (paper_ids_list,),
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

        logger.info(f"Migrated {len(repositories)} repositories")

        # Migrate project pages
        logger.info("Migrating project pages...")
        orig_cur.execute(
            """
            SELECT paper_id, url, is_official, source, created_at, updated_at
            FROM project_pages
            WHERE paper_id = ANY(%s)
        """,
            (paper_ids_list,),
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

        logger.info(f"Migrated {len(project_pages)} project pages")

        # Commit all changes
        new_conn.commit()
        logger.info("All data migrated successfully!")

        # Print final statistics
        logger.info("Migration Statistics:")
        logger.info("=" * 50)
        logger.info(f"Papers migrated: {len(papers):,}")
        logger.info(f"Authors migrated: {len(authors):,}")
        logger.info(f"Paper-author relationships: {len(paper_authors):,}")
        logger.info(f"Repositories migrated: {len(repositories):,}")
        logger.info(f"Project pages migrated: {len(project_pages):,}")
        logger.info("=" * 50)

    except Exception as e:
        new_conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        orig_conn.close()
        new_conn.close()


def main():
    """Main entry point."""
    logger = setup_logging("populate_hf_database")

    try:
        logger.info("Starting data migration to paperswithcode_hf database")

        # Load HF ArXiv IDs
        hf_arxiv_ids = load_hf_arxiv_ids()
        if not hf_arxiv_ids:
            logger.error("No HF ArXiv IDs loaded")
            return False

        # Migrate data
        migrate_papers_and_authors(hf_arxiv_ids)

        logger.info("🎉 Migration completed successfully!")
        logger.info(
            "The paperswithcode_hf database is now populated with HF papers and related data."
        )

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
