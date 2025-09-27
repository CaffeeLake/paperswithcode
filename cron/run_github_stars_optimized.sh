#!/bin/bash
#
# Optimized GitHub Stars CRON Job Wrapper
# Uses the new optimized script that groups repositories by owner/name
# Provides 10-100x efficiency improvement over the old script
#

# Set PATH for cron environment
export PATH="/root/.local/bin:$PATH"

# Set working directory
cd /root/python_projects/paperswithcode

# Create log file
LOG_FILE="/root/python_projects/paperswithcode/cron/logs/github_stars_optimized_$(date +%Y%m%d).log"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting optimized GitHub Stars job" | tee -a "$LOG_FILE"

# Check available memory before starting
AVAILABLE_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7}')
echo "$(date '+%Y-%m-%d %H:%M:%S') - Available memory: ${AVAILABLE_MEM}MB" | tee -a "$LOG_FILE"

# Don't start if less than 500MB available
if [ "$AVAILABLE_MEM" -lt 500 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Insufficient memory (${AVAILABLE_MEM}MB < 500MB)" | tee -a "$LOG_FILE"
    exit 1
fi

# Check environment file
if [ ! -f "backend/keys.env" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Environment file not found" | tee -a "$LOG_FILE"
    exit 1
fi

# Run with timeout and memory monitoring
timeout 50m uv run --env-file backend/keys.env cron/hourly/update_github_stars_optimized.py 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

# Check final memory state
FINAL_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7}')
echo "$(date '+%Y-%m-%d %H:%M:%S') - Final available memory: ${FINAL_MEM}MB" | tee -a "$LOG_FILE"

if [ $EXIT_CODE -eq 124 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Job timed out (50min limit)" | tee -a "$LOG_FILE"
    exit 0
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Job completed successfully" | tee -a "$LOG_FILE"
    exit 0
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Job failed with exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
    exit $EXIT_CODE
fi
