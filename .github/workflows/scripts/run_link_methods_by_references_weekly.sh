#!/bin/bash
#
# Wrapper script for the weekly references-based method tagging cron.
#
# Mirrors the layout of the other cron wrappers (see
# `run_citations_hourly.sh`): it sets PATH, PYTHONPATH, the working directory,
# verifies that backend/keys.env is present, then invokes the Python job under
# `uv` with the env file loaded.
#

export PATH="/root/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"

cd "$PROJECT_DIR" || exit 1

WRAPPER_LOG="$SCRIPT_DIR/logs/link_methods_by_references_wrapper_$(date +%Y%m%d).log"
mkdir -p "$SCRIPT_DIR/logs"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$WRAPPER_LOG"
}

log_message "Starting link_methods_by_references weekly cron wrapper"

if [ ! -f "backend/keys.env" ]; then
    log_message "ERROR: Environment file backend/keys.env not found"
    exit 1
fi

log_message "Environment file found, starting job"

if uv run --env-file backend/keys.env python -m scripts.weekly.link_methods_by_references "$@" 2>> "$WRAPPER_LOG"; then
    log_message "link_methods_by_references job completed successfully"
    exit 0
else
    EXIT_CODE=$?
    log_message "link_methods_by_references job failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
