#!/bin/bash
# Wrapper script for unified GitHub stars update CRON job
# This script uses flock to prevent overlapping runs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"
LOCKFILE="/tmp/github_stars.lock"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Run with flock to prevent overlaps
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date) - Another instance is running, exiting"
    exit 0
fi

# Run the unified GitHub stars update script de-prioritised (CPU + IO) and
# time-boxed so it cannot starve the API workers or run past the next hour.
timeout -k 60s 50m nice -n 19 ionice -c3 /root/.local/bin/uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars

# Release lock (automatic on exit, but explicit is clearer)
flock -u 200
