#!/bin/bash
#
# Wrapper script for Citations Hourly CRON Job
# This ensures proper environment loading and error handling for CRON execution
#

# Set PATH for cron environment
export PATH="/root/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"

# Set working directory
cd "$PROJECT_DIR" || exit 1

# Prevent overlapping runs piling up (hourly job; can hang on the Semantic
# Scholar API). Without this, stalled runs accumulate and starve the box.
LOCKFILE="/tmp/citations.lock"
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date) - Another citations instance is running, exiting"
    exit 0
fi

# Create log file for wrapper script errors
WRAPPER_LOG="$SCRIPT_DIR/logs/citations_wrapper_$(date +%Y%m%d).log"
mkdir -p "$SCRIPT_DIR/logs"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$WRAPPER_LOG"
}

log_message "Starting Citations Hourly CRON job wrapper"

# Check if environment file exists
if [ ! -f "backend/keys.env" ]; then
    log_message "ERROR: Environment file backend/keys.env not found"
    exit 1
fi

log_message "Environment file found, starting job"

# Run the job with proper error handling
# Job writes to its own log via DatabaseCronJob class, we just capture stderr to wrapper log
if timeout -k 60s 50m nice -n 19 ionice -c3 uv run --env-file backend/keys.env python -m scripts.hourly.update_citations 2>> "$WRAPPER_LOG"; then
    log_message "Citations job completed successfully"
    exit 0
else
    EXIT_CODE=$?
    log_message "Citations job failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
