#!/bin/bash
# Wrapper script for trending scores calculation CRON job
# This script uses flock to prevent overlapping runs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"
LOCKFILE="/tmp/trending_scores.lock"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Run with flock to prevent overlaps
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date) - Another instance is running, exiting"
    exit 0
fi

# Run the trending scores calculation script
/root/.local/bin/uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores

# Release lock (automatic on exit, but explicit is clearer)
flock -u 200
