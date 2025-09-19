#!/bin/bash

# Script to start the paper import in a detached screen session
# This allows the import to continue even if SSH connection is lost

SCRIPT_DIR="/root/python_projects/paperswithcode"
SESSION_NAME="papers_import"

echo "=== Starting PapersWithCode Import in Screen Session ==="
echo ""
echo "This will start a detached screen session that will:"
echo "1. Import ALL papers from the 2.3GB JSON file"
echo "2. Continue running even if your SSH connection drops"
echo "3. Log all progress to a timestamped log file"
echo ""

# Kill any existing session with the same name
screen -S "$SESSION_NAME" -X quit 2>/dev/null || true

echo "Starting screen session '$SESSION_NAME'..."
echo ""

# Start the import in a detached screen session
cd "$SCRIPT_DIR"
screen -dmS "$SESSION_NAME" bash -c "./run_full_import.sh"

echo "✅ Screen session '$SESSION_NAME' started successfully!"
echo ""
echo "To monitor the import progress:"
echo "  screen -r $SESSION_NAME    # Attach to the session"
echo "  screen -d $SESSION_NAME    # Detach from session (Ctrl+A, D)"
echo "  screen -list               # List all screen sessions"
echo ""
echo "To check logs:"
echo "  tail -f logs/papers_import_*.log"
echo ""
echo "To check current database status:"
echo "  sudo -u postgres psql -d paperswithcode -c \"SELECT COUNT(*) FROM papers;\""
echo ""

# Show current sessions
echo "Current screen sessions:"
screen -list
