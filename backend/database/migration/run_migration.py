#!/usr/bin/env python3
"""
Run the migration to add urls_extracted field to papers table.

Usage:
    uv run --env-file backend/keys.env backend/database/migration/run_migration.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the migration to add urls_extracted field."""

    # Database connection parameters
    db_params = {
        "host": os.getenv("PWC_DB_HOST", "localhost"),
        "port": os.getenv("PWC_DB_PORT", "5432"),
        "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("PWC_DB_USER", "postgres"),
        "password": os.getenv("PWC_DB_PASSWORD", ""),
    }

    try:
        # Connect to database
        logger.info("Connecting to database...")
        conn = psycopg2.connect(**db_params)
        conn.autocommit = True

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Read migration SQL
            migration_file = "/root/python_projects/paperswithcode/backend/database/migration/add_urls_extracted_field.sql"
            logger.info(f"Reading migration from {migration_file}")

            with open(migration_file, "r") as f:
                migration_sql = f.read()

            # Execute migration
            logger.info("Executing migration...")
            cur.execute(migration_sql)

            # Fetch and display results
            results = cur.fetchall()
            if results:
                result = results[0]
                logger.info("Migration completed successfully!")
                logger.info(f"Total papers: {result['total_papers']}")
                logger.info(
                    f"Papers already processed: {result['papers_already_processed']}"
                )
                logger.info(
                    f"Papers need processing: {result['papers_need_processing']}"
                )
                logger.info(
                    f"Percent already processed: {result['percent_already_processed']}%"
                )

        conn.close()
        logger.info("Migration completed successfully!")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    run_migration()
