#!/usr/bin/env bash
set -euo pipefail

CACHE_DIR="/var/cache/nginx/pwc"

if [[ ! -d "$CACHE_DIR" ]]; then
    echo "Nginx cache directory does not exist: $CACHE_DIR"
    exit 0
fi

rm -rf "${CACHE_DIR:?}"/*

if command -v nginx >/dev/null 2>&1; then
    nginx -t
    nginx -s reload
fi

echo "Purged Nginx proxy cache: $CACHE_DIR"
