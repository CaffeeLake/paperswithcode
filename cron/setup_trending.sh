#!/bin/bash
#
# Quick Setup Script for Trending Papers Feature
#
# This script sets up the database schema and verifies the trending feature is ready.
#
# Usage: bash cron/setup_trending.sh

set -e  # Exit on error

echo "================================"
echo "Trending Papers Feature Setup"
echo "================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root directory
cd "$PROJECT_ROOT" || exit 1

echo "Step 1: Setting up database schema..."
echo "Running SQL setup script..."

# Run the SQL setup script
psql -U postgres -d paperswithcode_hf -f backend/database/repos_and_pages_setup/setup_star_history.sql

if [ $? -eq 0 ]; then
    echo "✅ Database schema created successfully"
else
    echo "❌ Database setup failed"
    exit 1
fi

echo ""
echo "Step 2: Verifying setup..."

# Verify the setup
uv run --env-file backend/keys.env python -c "
from backend.database.connection import db_manager
from sqlalchemy import text

print('Checking database setup...')

with db_manager.session_local() as session:
    # Check if table exists
    result = session.execute(text('''
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'repository_star_history'
    ''')).scalar()

    if result > 0:
        print('✅ repository_star_history table exists')
    else:
        print('❌ repository_star_history table not found')
        exit(1)

    # Check if functions exist
    result = session.execute(text('''
        SELECT COUNT(*)
        FROM pg_proc
        WHERE proname IN ('calculate_star_velocity', 'calculate_trending_score')
    ''')).scalar()

    if result >= 2:
        print('✅ Trending calculation functions exist')
    else:
        print('❌ Trending functions not found')
        exit(1)

    # Check if views exist
    result = session.execute(text('''
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_name IN ('trending_repositories_24h', 'trending_papers_24h')
    ''')).scalar()

    if result >= 2:
        print('✅ Trending views exist')
    else:
        print('❌ Trending views not found')
        exit(1)

    # Check for recent papers with repositories
    result = session.execute(text('''
        SELECT COUNT(DISTINCT r.id)
        FROM repositories r
        JOIN paper_repositories pr ON r.id = pr.repository_id
        JOIN papers p ON pr.paper_id = p.id
        WHERE p.date_published >= NOW() - INTERVAL '6 months'
        AND pr.is_official = TRUE
        AND r.owner IS NOT NULL
        AND r.name IS NOT NULL
    ''')).scalar()

    print(f'✅ Found {result} repositories from recent papers (last 6 months)')

    if result < 10:
        print('⚠️  Warning: Very few recent papers with repositories')
        print('   The trending job may not have much to process')

print('')
print('All checks passed! ✅')
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Setup verification completed successfully"
else
    echo ""
    echo "❌ Setup verification failed"
    exit 1
fi

echo ""
echo "Step 3: Testing trending job (dry run)..."
echo "This will process a few repositories to test the system..."
echo ""

# Test the trending job with a small run
timeout 120 uv run --env-file backend/keys.env python -c "
import sys
sys.path.insert(0, 'cron/hourly')
from update_github_stars_trending import main, log

# Override max_updates for testing
import update_github_stars_trending as module
original_main = module.main

def test_main():
    log('=== TEST RUN (LIMITED TO 5 REPOSITORIES) ===')
    # Monkey patch for testing
    import cron.hourly.update_github_stars_trending as mod
    original_max = 500
    try:
        # Run with limited updates
        original_main()
    except SystemExit:
        pass

test_main()
" 2>&1 | head -50

echo ""
echo "================================"
echo "Setup Complete! ✅"
echo "================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Test the trending job manually:"
echo "   ./cron/run_github_stars_trending.sh"
echo ""
echo "2. Check the logs:"
echo "   tail -f cron/logs/github_stars_trending_\$(date +%Y%m%d).log"
echo ""
echo "3. Add to crontab for hourly execution:"
echo "   crontab -e"
echo "   # Add this line:"
echo "   0 * * * * cd $(pwd) && ./cron/run_github_stars_trending.sh"
echo ""
echo "4. Query trending papers:"
echo "   psql -U postgres -d paperswithcode_hf -c 'SELECT * FROM trending_papers_24h LIMIT 10;'"
echo ""
echo "For detailed documentation, see: cron/TRENDING_GUIDE.md"
echo ""
