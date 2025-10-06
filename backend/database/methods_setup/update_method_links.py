#!/usr/bin/env python3
"""
Update legacy paperswithcode.com links in method descriptions to point to the new website.

This script replaces:
- https://paperswithcode.com/method/{name} → http://167.235.148.241:8080/methods/{name}
- http://paperswithcode.com/method/{name} → http://167.235.148.241:8080/methods/{name}
- https://paperswithcode.com/methods/category/{name} → http://167.235.148.241:8080/methods (category pages don't exist yet)
"""

import re
import sys
import psycopg2
from typing import List, Tuple

# Database connection settings
DB_CONFIG = {
    "dbname": "paperswithcode_hf",
    "user": "paperswithcode_user",
    "password": "paperswithcode123",
    "host": "localhost",
    "port": "5432",
}

# New website base URL
NEW_BASE_URL = "http://167.235.148.241:8080"


def get_db_connection():
    """Create and return a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def get_methods_with_links(conn) -> List[Tuple[int, str, str]]:
    """Get all methods that have paperswithcode.com links in their descriptions."""
    cursor = conn.cursor()

    query = """
        SELECT id, name, description
        FROM methods
        WHERE description IS NOT NULL
          AND (description LIKE '%paperswithcode.com/method/%'
               OR description LIKE '%paperswithcode.com/methods/%')
        ORDER BY id;
    """

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()

    return results


def update_description_links(description: str) -> str:
    """
    Update paperswithcode.com links in the description to point to the new website.

    Args:
        description: Original description text

    Returns:
        Updated description text
    """
    if not description:
        return description

    # Pattern 1: Replace https://paperswithcode.com/method/{name} → new URL
    description = re.sub(
        r"https?://paperswithcode\.com/method/([a-zA-Z0-9_-]+)",
        f"{NEW_BASE_URL}/methods/\\1",
        description,
        flags=re.IGNORECASE,
    )

    # Pattern 2: Replace https://paperswithcode.com/methods/category/{name} → new URL
    # Note: We'll just link to /methods for now since we don't have category pages
    description = re.sub(
        r"https?://paperswithcode\.com/methods/category/([a-zA-Z0-9_-]+)",
        f"{NEW_BASE_URL}/methods",
        description,
        flags=re.IGNORECASE,
    )

    return description


def update_methods(conn, dry_run: bool = False) -> None:
    """
    Update all method descriptions with new links.

    Args:
        conn: Database connection
        dry_run: If True, only show what would be changed without updating
    """
    methods = get_methods_with_links(conn)

    if not methods:
        print("No methods found with paperswithcode.com links.")
        return

    print(f"Found {len(methods)} methods with paperswithcode.com links.\n")

    cursor = conn.cursor()
    updated_count = 0

    for method_id, method_name, old_description in methods:
        new_description = update_description_links(old_description)

        if old_description != new_description:
            print(f"Method: {method_name} (ID: {method_id})")

            # Show changes
            if old_description != new_description:
                # Extract and show the changed URLs
                old_urls = re.findall(
                    r"https?://paperswithcode\.com/method[s]?/[a-zA-Z0-9_/-]+",
                    old_description,
                )
                new_urls = re.findall(
                    f"{re.escape(NEW_BASE_URL)}/methods/[a-zA-Z0-9_/-]*",
                    new_description,
                )

                if old_urls:
                    print(f"  Old URLs: {old_urls[:3]}")  # Show first 3
                    if len(old_urls) > 3:
                        print(f"  ... and {len(old_urls) - 3} more")

                if new_urls:
                    print(f"  New URLs: {new_urls[:3]}")  # Show first 3
                    if len(new_urls) > 3:
                        print(f"  ... and {len(new_urls) - 3} more")

            if not dry_run:
                # Update the database
                update_query = """
                    UPDATE methods
                    SET description = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """
                cursor.execute(update_query, (new_description, method_id))
                updated_count += 1

            print()

    if not dry_run:
        conn.commit()
        print(f"✅ Successfully updated {updated_count} method descriptions.")
    else:
        print(f"DRY RUN: Would update {len(methods)} method descriptions.")
        print("Run without --dry-run to apply changes.")

    cursor.close()


def verify_updates(conn) -> None:
    """Verify that all links have been updated."""
    cursor = conn.cursor()

    # Check for remaining old links
    query = """
        SELECT COUNT(*) as remaining
        FROM methods
        WHERE description IS NOT NULL
          AND (description LIKE '%paperswithcode.com/method/%'
               OR description LIKE '%paperswithcode.com/methods/%');
    """

    cursor.execute(query)
    result = cursor.fetchone()
    remaining = result[0] if result else 0

    # Check for new links
    query_new = """
        SELECT COUNT(*) as updated
        FROM methods
        WHERE description LIKE %s;
    """

    cursor.execute(query_new, (f"%{NEW_BASE_URL}/methods/%",))
    result = cursor.fetchone()
    updated = result[0] if result else 0

    cursor.close()

    print("\n" + "=" * 70)
    print("Verification Results:")
    print("=" * 70)
    print(f"Methods with old paperswithcode.com links: {remaining}")
    print(f"Methods with new {NEW_BASE_URL} links: {updated}")

    if remaining == 0:
        print("✅ All links successfully updated!")
    else:
        print(f"⚠️  Warning: {remaining} methods still have old links")


def main():
    """Main function to update method links."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Update paperswithcode.com links in method descriptions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without updating",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Method Links Update Script")
    print("=" * 70)
    print()

    # Connect to database
    print("Connecting to database...")
    conn = get_db_connection()

    try:
        # Update methods
        update_methods(conn, dry_run=args.dry_run)

        # Verify updates (only if not dry run)
        if not args.dry_run:
            verify_updates(conn)

        print("\n" + "=" * 70)
        print("Update completed!")
        print("=" * 70)

    except Exception as e:
        print(f"\nError during update: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
