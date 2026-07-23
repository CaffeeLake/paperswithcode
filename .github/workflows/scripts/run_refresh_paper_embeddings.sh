#!/bin/bash
# Wrapper for the bounded hourly active-generation embedding refresh.

set -u

export PATH="/root/.local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"
LOCKFILE="/tmp/refresh_paper_embeddings.lock"

cd "$PROJECT_DIR" || exit 1

exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date) - Another paper embedding refresh is running, exiting"
    exit 0
fi

timeout -k 30s 20m nice -n 19 ionice -c3 \
    uv run --env-file backend/keys.env \
    python -m scripts.hourly.refresh_paper_embeddings
