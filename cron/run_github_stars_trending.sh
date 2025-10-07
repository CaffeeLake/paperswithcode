#!/bin/bash
#
# GitHub Stars Trending Update - Hourly CRON Job Runner
#
# This script runs the trending-focused GitHub stars update job.
# It prioritizes recent papers (last 6 months) and updates their star
# counts every 1-2 hours to enable accurate trending metrics.
#
# Schedule: Hourly (0 * * * *)
# Purpose: Track star velocity for trending paper detection
# Separate from: Regular stars update job (7-day refresh for all papers)
#
# Usage: cron/run_github_stars_trending.sh

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root directory
cd "$PROJECT_ROOT" || exit 1

# Set up logging
DATE=$(date +%Y%m%d)
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/github_stars_trending_${DATE}.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log start time
echo "============================================================" >> "$LOG_FILE"
echo "Starting trending GitHub Stars job at $(date)" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"

# Check available memory
AVAILABLE_MEM=$(free -m | awk '/^Mem:/{print $7}')
echo "Available memory: ${AVAILABLE_MEM}MB" >> "$LOG_FILE"

if [ "$AVAILABLE_MEM" -lt 300 ]; then
    echo "WARNING: Low memory (${AVAILABLE_MEM}MB). Job may fail." >> "$LOG_FILE"
fi

# Run the trending stars update job
echo "Starting optimized trending stars update..." >> "$LOG_FILE"
uv run --env-file backend/keys.env python cron/hourly/update_github_stars_trending.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

# Log completion
echo "============================================================" >> "$LOG_FILE"
if [ $EXIT_CODE -eq 0 ]; then
    echo "Job completed successfully at $(date)" >> "$LOG_FILE"
else
    echo "Job failed with exit code $EXIT_CODE at $(date)" >> "$LOG_FILE"
fi

# Check available memory after job
AVAILABLE_MEM_AFTER=$(free -m | awk '/^Mem:/{print $7}')
echo "Final available memory: ${AVAILABLE_MEM_AFTER}MB" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"

exit $EXIT_CODE
