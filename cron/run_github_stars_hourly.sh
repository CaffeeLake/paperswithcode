#!/bin/bash
#
# Wrapper script for GitHub Stars Hourly CRON Job
# This ensures proper environment loading and error handling for CRON execution
#

# Set PATH for cron environment
export PATH="/root/.local/bin:$PATH"

# Set working directory
cd /root/python_projects/paperswithcode

# Create log file for wrapper script errors
WRAPPER_LOG="/root/python_projects/paperswithcode/cron/logs/github_stars_wrapper_$(date +%Y%m%d).log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$WRAPPER_LOG"
}

log_message "Starting GitHub Stars Hourly CRON job wrapper"

# Check if environment file exists
if [ ! -f "backend/keys.env" ]; then
    log_message "ERROR: Environment file backend/keys.env not found"
    exit 1
fi

log_message "Environment file found, starting job"

# Run the job with proper error handling
if uv run --env-file backend/keys.env cron/hourly/update_github_stars.py >> "$WRAPPER_LOG" 2>&1; then
    log_message "GitHub Stars job completed successfully"
    exit 0
else
    EXIT_CODE=$?
    log_message "GitHub Stars job failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
