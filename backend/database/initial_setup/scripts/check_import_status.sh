#!/bin/bash

# Quick script to check the status of the paper import

echo "=== PapersWithCode Import Status ==="
echo ""

# Check if screen session is running
if screen -list | grep -q "papers_import"; then
    echo "✅ Import session is RUNNING"
    echo "   Session: papers_import"
    echo "   To attach: screen -r papers_import"
else
    echo "❌ No import session found"
    echo "   The import may have finished or stopped"
fi

echo ""

# Current paper count
echo "📊 Current database status:"
sudo -u postgres psql -d paperswithcode -c "
SELECT 
    COUNT(*) as total_papers,
    MIN(date_published) as earliest_paper,
    MAX(date_published) as latest_paper
FROM papers;" 2>/dev/null || echo "Error: Could not connect to database"

echo ""

# Check for log files
LOG_DIR="/root/python_projects/paperswithcode/logs"
if [ -d "$LOG_DIR" ]; then
    echo "📋 Recent log files:"
    ls -lt "$LOG_DIR"/*.log 2>/dev/null | head -3 || echo "No log files found"
    echo ""
    
    # Show last few lines of most recent log
    LATEST_LOG=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "📄 Last 10 lines of most recent log:"
        echo "   File: $LATEST_LOG"
        echo "   ----------------------------------------"
        tail -10 "$LATEST_LOG"
    fi
else
    echo "📋 No logs directory found"
fi

echo ""
echo "To monitor live progress: tail -f logs/papers_import_*.log"
