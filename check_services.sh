#!/usr/bin/env sh
set -eu
if command -v pwc-status >/dev/null 2>&1; then
    exec pwc-status "$@"
fi
echo "pwc-status is not installed yet; run deploy/topology_audit.py for a read-only audit." >&2
exec python3 "$(dirname "$0")/deploy/topology_audit.py" "$@"
