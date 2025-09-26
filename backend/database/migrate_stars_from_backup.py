#!/usr/bin/env python3
"""
Migrate Stars from RepositoryBackup Script

This script migrates the num_stars information from the RepositoryBackup table
to the current Repository table by matching repositories based on their URLs.

Usage:
    uv run backend/database/migrate_stars_from_backup.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

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


class StarsMigrator:
    """Handles migration of stars data from backup to current repository table."""

    def __init__(self):
        self.db_params = DB_PARAMS
        print(f"🔗 Connecting to database: {self.db_params['database']}")

    def get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(**self.db_params)

    def normalize_url(self, url: str) -> str:
        """Normalize URL for comparison by removing trailing slashes and converting to lowercase."""
        if not url:
            return ""

        # Remove trailing slash and convert to lowercase for consistent comparison
        normalized = url.rstrip("/").lower()

        # Handle common GitHub URL variations
        if "github.com" in normalized:
            # Remove .git suffix if present
            if normalized.endswith(".git"):
                normalized = normalized[:-4]

        return normalized

    def get_backup_stars_data(self) -> Dict[str, int]:
        """Get stars data from the RepositoryBackup table."""
        print("📊 Fetching stars data from RepositoryBackup table...")

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT url, num_stars
                    FROM repositorybackup
                    WHERE num_stars > 0
                    ORDER BY num_stars DESC
                """)

                backup_data = {}
                total_repos = 0
                repos_with_stars = 0

                for row in cur.fetchall():
                    total_repos += 1
                    url = row["url"]
                    stars = row["num_stars"]

                    if stars and stars > 0:
                        repos_with_stars += 1
                        normalized_url = self.normalize_url(url)
                        backup_data[normalized_url] = stars

                print(f"📊 Found {total_repos:,} repositories in backup")
                print(f"⭐ Found {repos_with_stars:,} repositories with stars > 0")
                print(f"📊 Created mapping for {len(backup_data):,} normalized URLs")

                return backup_data

    def get_current_repositories(self) -> List[Tuple[int, str, int]]:
        """Get current repositories that need stars updates."""
        print("📊 Fetching current repositories...")

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, url, num_stars
                    FROM repositories
                    ORDER BY id
                """)

                repositories = []
                for row in cur.fetchall():
                    repositories.append((row["id"], row["url"], row["num_stars"]))

                print(f"📊 Found {len(repositories):,} current repositories")
                return repositories

    def migrate_stars(self):
        """Migrate stars from backup to current repositories."""
        print("\n🌟 Starting stars migration...")

        # Get backup stars data
        backup_stars = self.get_backup_stars_data()

        if not backup_stars:
            print("❌ No stars data found in backup table")
            return

        # Get current repositories
        current_repos = self.get_current_repositories()

        # Process migrations
        updates = []
        matches_found = 0
        no_matches = 0
        already_has_stars = 0

        for repo_id, url, current_stars in current_repos:
            normalized_url = self.normalize_url(url)

            if normalized_url in backup_stars:
                backup_star_count = backup_stars[normalized_url]

                # Only update if current stars is 0 or less than backup stars
                if current_stars == 0 or backup_star_count > current_stars:
                    updates.append((backup_star_count, repo_id))
                    matches_found += 1
                else:
                    already_has_stars += 1
            else:
                no_matches += 1

        print("\n📊 Migration Analysis:")
        print(f"   ✅ Matches found: {matches_found:,}")
        print(f"   ⭐ Already has stars: {already_has_stars:,}")
        print(f"   ❌ No matches: {no_matches:,}")

        if not updates:
            print(
                "ℹ️  No updates needed - all repositories already have current star counts"
            )
            return

        # Perform batch update
        print(f"\n🔄 Updating {len(updates):,} repositories with star counts...")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Batch update using execute_values
                update_query = """
                    UPDATE repositories
                    SET num_stars = data.stars,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS data(stars, repo_id)
                    WHERE repositories.id = data.repo_id
                """

                try:
                    psycopg2.extras.execute_values(
                        cur, update_query, updates, template=None, page_size=1000
                    )
                    conn.commit()
                    print(
                        f"✅ Successfully updated {len(updates):,} repositories with star counts"
                    )

                except Exception as e:
                    print(f"❌ Error during batch update: {e}")
                    conn.rollback()
                    raise

    def verify_migration(self):
        """Verify the migration results."""
        print("\n🔍 Verifying migration results...")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Check current star statistics
                cur.execute("""
                    SELECT
                        COUNT(*) as total_repos,
                        COUNT(CASE WHEN num_stars > 0 THEN 1 END) as repos_with_stars,
                        MAX(num_stars) as max_stars,
                        AVG(CASE WHEN num_stars > 0 THEN num_stars END) as avg_stars
                    FROM repositories
                """)

                stats = cur.fetchone()
                total_repos, repos_with_stars, max_stars, avg_stars = stats

                print("📊 Current Repository Statistics:")
                print(f"   Total repositories: {total_repos:,}")
                print(f"   Repositories with stars: {repos_with_stars:,}")
                print(f"   Max stars: {max_stars:,}")
                print(f"   Average stars (for repos with stars): {avg_stars:.1f}")

                # Show top repositories by stars
                cur.execute("""
                    SELECT url, owner, name, num_stars
                    FROM repositories
                    WHERE num_stars > 0
                    ORDER BY num_stars DESC
                    LIMIT 10
                """)

                print("\n🏆 Top 10 Repositories by Stars:")
                for row in cur.fetchall():
                    url, owner, name, stars = row
                    repo_name = f"{owner}/{name}" if owner and name else url
                    print(f"   ⭐ {stars:,} - {repo_name}")

    def show_migration_summary(self):
        """Show a summary comparison between backup and current data."""
        print("\n📋 Migration Summary:")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Backup table stats
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN num_stars > 0 THEN 1 END) as with_stars,
                        MAX(num_stars) as max_stars
                    FROM repositorybackup
                """)
                backup_stats = cur.fetchone()

                # Current table stats
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN num_stars > 0 THEN 1 END) as with_stars,
                        MAX(num_stars) as max_stars
                    FROM repositories
                """)
                current_stats = cur.fetchone()

                print(
                    f"📊 RepositoryBackup: {backup_stats[0]:,} total, {backup_stats[1]:,} with stars, max: {backup_stats[2]:,}"
                )
                print(
                    f"📊 Current Repository: {current_stats[0]:,} total, {current_stats[1]:,} with stars, max: {current_stats[2]:,}"
                )

    def run(self):
        """Run the complete stars migration process."""
        print("🌟 Starting Repository Stars Migration")
        print(f"📁 Using database: {self.db_params['database']}")

        try:
            # Show initial summary
            self.show_migration_summary()

            # Perform migration
            self.migrate_stars()

            # Verify results
            self.verify_migration()

            print("\n🎉 Stars migration completed successfully!")

        except Exception as e:
            print(f"\n❌ Error during migration: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


def main():
    """Main function."""
    migrator = StarsMigrator()
    migrator.run()


if __name__ == "__main__":
    main()
