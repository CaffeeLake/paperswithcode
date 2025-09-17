#!/bin/bash

# Streaming Papers Import Script - Memory-Safe Version
# This script runs the paper import using streaming to avoid memory issues

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="/root/python_projects/paperswithcode"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/streaming_import_$(date +%Y%m%d_%H%M%S).log"

# Create logs directory
mkdir -p "$LOG_DIR"

echo "=== PapersWithCode Streaming Import Script ===" | tee -a "$LOG_FILE"
echo "Started at: $(date)" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Check current paper count
echo "Current papers in database:" | tee -a "$LOG_FILE"
sudo -u postgres psql -d paperswithcode -c "SELECT COUNT(*) as total_papers FROM papers;" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Check available memory
echo "Available memory:" | tee -a "$LOG_FILE"
free -h | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Change to project directory
cd "$SCRIPT_DIR"

echo "Starting STREAMING import..." | tee -a "$LOG_FILE"
echo "This version processes papers one by one to avoid memory issues" | tee -a "$LOG_FILE"
echo "Progress will be logged to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Run the streaming import with proper Python path and logging
PYTHONPATH="$SCRIPT_DIR" uv run python backend/database/setup/add_pwc_papers_streaming.py \
    --json-file data/papers-with-abstracts.json \
    --user postgres \
    --password postgres \
    --batch-size 500 \
    2>&1 | tee -a "$LOG_FILE"

# Final status
echo "" | tee -a "$LOG_FILE"
echo "=== Import Completed at: $(date) ===" | tee -a "$LOG_FILE"
echo "Final papers count:" | tee -a "$LOG_FILE"
sudo -u postgres psql -d paperswithcode -c "SELECT COUNT(*) as total_papers FROM papers;" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "Streaming import script finished. Check log file for details: $LOG_FILE"
