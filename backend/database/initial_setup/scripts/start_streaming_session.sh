#!/bin/bash

# Script to start the STREAMING paper import in a detached screen session
# This version avoids memory issues by processing papers one by one

SCRIPT_DIR="/root/python_projects/paperswithcode"
SESSION_NAME="streaming_import"

echo "=== Starting PapersWithCode STREAMING Import in Screen Session ==="
echo ""
echo "🔧 MEMORY-SAFE VERSION 🔧"
echo ""
echo "This will start a detached screen session that will:"
echo "1. Import ALL papers from the 2.3GB JSON file using STREAMING"
echo "2. Process papers one by one to avoid memory issues"
echo "3. Continue running even if your SSH connection drops"
echo "4. Log all progress to a timestamped log file"
echo ""

# Kill any existing session with the same name
screen -S "$SESSION_NAME" -X quit 2>/dev/null || true

echo "Starting screen session '$SESSION_NAME'..."
echo ""

# Start the import in a detached screen session
cd "$SCRIPT_DIR"
screen -dmS "$SESSION_NAME" bash -c "./run_streaming_import.sh"

echo "✅ Screen session '$SESSION_NAME' started successfully!"
echo ""
echo "To monitor the import progress:"
echo "  screen -r $SESSION_NAME    # Attach to the session"
echo "  screen -d $SESSION_NAME    # Detach from session (Ctrl+A, D)"
echo "  screen -list               # List all screen sessions"
echo ""
echo "To check logs:"
echo "  tail -f logs/streaming_import_*.log"
echo ""
echo "To check current database status:"
echo "  sudo -u postgres psql -d paperswithcode -c \"SELECT COUNT(*) FROM papers;\""
echo ""

# Show current sessions
echo "Current screen sessions:"
screen -list
