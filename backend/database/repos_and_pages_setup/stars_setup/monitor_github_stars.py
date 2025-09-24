#!/usr/bin/env python3
"""
Monitor GitHub Stars Population Progress

This script checks the current progress of the GitHub stars population process.
"""

from datetime import datetime
from backend.database.connection import get_database_session
from sqlalchemy import text


def main():
    print("🔍 GitHub Stars Population Monitor")
    print("=" * 60)

    db_session_gen = get_database_session()
    db = next(db_session_gen)

    try:
        # Get current statistics
        result = db.execute(
            text("""
            SELECT COUNT(*) as total
            FROM repositories
            WHERE owner IS NOT NULL AND name IS NOT NULL
        """)
        )
        total_repos = result.fetchone().total

        result = db.execute(
            text("""
            SELECT COUNT(*) as completed
            FROM repositories
            WHERE owner IS NOT NULL AND name IS NOT NULL AND num_stars > 0
        """)
        )
        completed_repos = result.fetchone().completed

        result = db.execute(
            text("""
            SELECT COUNT(*) as remaining
            FROM repositories
            WHERE owner IS NOT NULL AND name IS NOT NULL
            AND (num_stars IS NULL OR num_stars = 0)
        """)
        )
        remaining_repos = result.fetchone().remaining

        # Calculate progress
        progress_percent = (
            (completed_repos / total_repos) * 100 if total_repos > 0 else 0
        )

        # Get some recent updates
        result = db.execute(
            text("""
            SELECT owner, name, num_stars, updated_at
            FROM repositories
            WHERE owner IS NOT NULL AND name IS NOT NULL AND num_stars > 0
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        )
        recent_updates = result.fetchall()

        # Display results
        print("📊 Progress Statistics:")
        print(f"   Total repositories: {total_repos:,}")
        print(f"   Completed: {completed_repos:,}")
        print(f"   Remaining: {remaining_repos:,}")
        print(f"   Progress: {progress_percent:.2f}%")
        print()

        if remaining_repos > 0:
            # Estimate remaining time (assuming 4500 repos/hour)
            estimated_hours = remaining_repos / 4500
            print(f"⏱️  Estimated time remaining: {estimated_hours:.1f} hours")
            print()

        if recent_updates:
            print("🆕 Recent Updates:")
            for repo in recent_updates:
                print(
                    f"   {repo.owner}/{repo.name}: {repo.num_stars:,} stars ({repo.updated_at})"
                )

        print(f"\n🕐 Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if progress_percent >= 100:
            print("\n🎉 GitHub stars population completed!")
        elif completed_repos > 0:
            print(
                f"\n✅ Process is running... {completed_repos:,} repositories processed so far"
            )
        else:
            print("\n⏳ Process may be starting up or encountering issues...")

    finally:
        db.close()


if __name__ == "__main__":
    main()
