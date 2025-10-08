#!/usr/bin/env python3
"""
Verification script for EMA Trending System.

Run this script to check if the trending system is working correctly.
Usage: uv run --env-file backend/keys.env cron/verify_trending_system.py
"""

from datetime import datetime
from backend.database.connection import db_manager
from sqlalchemy import text


def print_section(title):
    """Print a section header."""
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)


def check_database_schema():
    """Check if trending columns exist."""
    print_section("1. DATABASE SCHEMA CHECK")

    session = db_manager.session_local()
    try:
        result = session.execute(
            text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'repositories'
            AND column_name IN ('trending_score', 'trending_score_updated_at')
            ORDER BY column_name;
        """)
        ).fetchall()

        if len(result) == 2:
            print("✅ Trending columns exist in repositories table:")
            for row in result:
                print(f"   - {row[0]}: {row[1]} (nullable: {row[2]})")
        else:
            print("❌ Trending columns not found! Run migration:")
            print(
                "   uv run --env-file backend/keys.env backend/database/migrations/run_add_trending_score.py"
            )
            return False

        # Check indexes
        result = session.execute(
            text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'repositories'
            AND indexname LIKE '%trending%'
            ORDER BY indexname;
        """)
        ).fetchall()

        if result:
            print(f"\n✅ Found {len(result)} trending indexes:")
            for row in result:
                print(f"   - {row[0]}")

        return True

    finally:
        session.close()


def check_snapshots():
    """Check historical snapshots."""
    print_section("2. HISTORICAL SNAPSHOTS CHECK")

    session = db_manager.session_local()
    try:
        # Overall stats
        result = session.execute(
            text("""
            SELECT
                COUNT(*) as total,
                MIN(snapshot_at) as oldest,
                MAX(snapshot_at) as newest,
                COUNT(DISTINCT repository_id) as unique_repos
            FROM repository_star_history;
        """)
        ).fetchone()

        print(f"Total snapshots: {result[0]:,}")
        print(f"Unique repositories: {result[3]:,}")
        print(f"Date range: {result[1]} → {result[2]}")

        if result[0] == 0:
            print("\n⚠️  No snapshots found!")
            print("   Wait for GitHub stars update job to run (hourly at :00)")
            return False

        # Recent snapshots (last 24 hours)
        result = session.execute(
            text("""
            SELECT COUNT(*) as recent_count
            FROM repository_star_history
            WHERE snapshot_at >= NOW() - INTERVAL '24 hours';
        """)
        ).fetchone()

        print(f"\nSnapshots in last 24 hours: {result[0]:,}")

        if result[0] == 0:
            print("⚠️  No recent snapshots! Check if CRON job is running:")
            print("   tail -f cron/logs/github_stars_cron_$(date +%Y%m%d).log")
            return False

        print("✅ Snapshots are being collected")
        return True

    finally:
        session.close()


def check_trending_scores():
    """Check trending score calculation."""
    print_section("3. TRENDING SCORES CHECK")

    session = db_manager.session_local()
    try:
        # Overall stats
        result = session.execute(
            text("""
            SELECT
                COUNT(*) as total_repos,
                COUNT(trending_score) as with_scores,
                COUNT(CASE WHEN trending_score > 0 THEN 1 END) as positive_scores,
                MIN(trending_score) as min_score,
                MAX(trending_score) as max_score,
                AVG(trending_score) as avg_score
            FROM repositories;
        """)
        ).fetchone()

        total = result[0]
        with_scores = result[1]
        positive = result[2]

        print(f"Total repositories: {total:,}")
        print(
            f"With trending scores: {with_scores:,} ({with_scores / total * 100:.1f}%)"
        )
        print(f"With positive scores: {positive:,} ({positive / total * 100:.1f}%)")

        if with_scores > 0:
            print("\nScore statistics:")
            print(f"  Min: {result[3]:.4f} stars/hour")
            print(f"  Max: {result[4]:.4f} stars/hour")
            print(f"  Avg: {result[5]:.4f} stars/hour")

        # Recent updates
        result = session.execute(
            text("""
            SELECT COUNT(*) as recent_updates
            FROM repositories
            WHERE trending_score_updated_at >= NOW() - INTERVAL '2 hours';
        """)
        ).fetchone()

        print(f"\nTrending scores updated in last 2 hours: {result[0]:,}")

        if result[0] == 0 and positive > 0:
            print(
                "⚠️  No recent updates! Check if trending calculation CRON is running:"
            )
            print("   tail -f cron/logs/trending_scores_cron_$(date +%Y%m%d).log")
            return False
        elif positive == 0:
            print("⚠️  No positive trending scores yet!")
            print(
                "   This is normal in the first 24 hours. Repos need 2+ snapshots to calculate velocity."
            )
            return True

        print("✅ Trending scores are being calculated")
        return True

    finally:
        session.close()


def check_top_trending():
    """Show top trending repositories."""
    print_section("4. TOP TRENDING REPOSITORIES")

    session = db_manager.session_local()
    try:
        result = session.execute(
            text("""
            SELECT
                r.owner,
                r.name,
                r.num_stars,
                r.trending_score,
                r.trending_score_updated_at,
                COUNT(DISTINCT p.id) as paper_count
            FROM repositories r
            LEFT JOIN paper_repositories pr ON r.id = pr.repository_id
            LEFT JOIN papers p ON pr.paper_id = p.id
            WHERE r.trending_score IS NOT NULL
            AND r.trending_score > 0
            GROUP BY r.id, r.owner, r.name, r.num_stars, r.trending_score, r.trending_score_updated_at
            ORDER BY r.trending_score DESC
            LIMIT 10;
        """)
        ).fetchall()

        if result:
            print(f"\nTop {len(result)} trending repositories:\n")
            for i, row in enumerate(result, 1):
                owner, name, stars, score, updated, papers = row
                age = ""
                if updated:
                    hours_ago = (
                        datetime.now() - updated.replace(tzinfo=None)
                    ).total_seconds() / 3600
                    age = f" ({hours_ago:.1f}h ago)"

                print(f"  {i:2d}. {owner}/{name}")
                print(
                    f"      ⭐ {stars:,} stars | 🔥 {score:.4f} stars/hour | 📄 {papers} papers{age}"
                )
        else:
            print("⚠️  No trending repositories found yet")
            print(
                "   Wait for trending calculation to run (needs 2+ snapshots per repo)"
            )

        return len(result) > 0

    finally:
        session.close()


def check_cron_jobs():
    """Check if CRON jobs are configured."""
    print_section("5. CRON CONFIGURATION CHECK")

    import subprocess

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        crontab = result.stdout

        has_stars = "github_stars" in crontab and "run_github_stars.sh" in crontab
        has_trending = (
            "trending_scores" in crontab and "run_trending_scores.sh" in crontab
        )

        if has_stars:
            print("✅ GitHub stars update CRON job configured")
        else:
            print("❌ GitHub stars update CRON job NOT configured")
            print("   Add to crontab: 0 * * * * .../run_github_stars.sh")

        if has_trending:
            print("✅ Trending calculation CRON job configured")
        else:
            print("❌ Trending calculation CRON job NOT configured")
            print("   Add to crontab: 30 * * * * .../run_trending_scores.sh")

        return has_stars and has_trending

    except Exception as e:
        print(f"⚠️  Could not check crontab: {e}")
        return False


def check_api_models():
    """Check if API models include trending fields."""
    print_section("6. API MODELS CHECK")

    try:
        from backend.models.api import Repository
        from backend.models.database import Repository as DBRepository

        # Check API model
        api_fields = Repository.model_fields.keys()
        has_api_trending = "trending_score" in api_fields
        has_api_updated = "trending_score_updated_at" in api_fields

        if has_api_trending and has_api_updated:
            print("✅ API Repository model includes trending fields")
        else:
            print("❌ API Repository model missing trending fields")
            return False

        # Check database model
        db_fields = [c.name for c in DBRepository.__table__.columns]
        has_db_trending = "trending_score" in db_fields
        has_db_updated = "trending_score_updated_at" in db_fields

        if has_db_trending and has_db_updated:
            print("✅ Database Repository model includes trending fields")
        else:
            print("❌ Database Repository model missing trending fields")
            return False

        return True

    except Exception as e:
        print(f"⚠️  Could not check models: {e}")
        return False


def main():
    """Run all verification checks."""
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  EMA TRENDING SYSTEM VERIFICATION".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    results = []

    # Run checks
    results.append(("Database Schema", check_database_schema()))
    results.append(("Historical Snapshots", check_snapshots()))
    results.append(("Trending Scores", check_trending_scores()))
    results.append(("Top Trending", check_top_trending()))
    results.append(("CRON Configuration", check_cron_jobs()))
    results.append(("API Models", check_api_models()))

    # Summary
    print_section("VERIFICATION SUMMARY")
    print()

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")

    print()
    print(f"Overall: {passed}/{total} checks passed ({passed / total * 100:.0f}%)")
    print()

    if passed == total:
        print("🎉 ALL CHECKS PASSED! System is fully operational.")
    elif passed >= total * 0.8:
        print("⚠️  MOSTLY WORKING. Some features may need time to fully activate.")
        print("   (Normal in first 24-48 hours after deployment)")
    else:
        print("❌ ISSUES DETECTED. Review failed checks above.")

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
