#!/usr/bin/env bash
set -euo pipefail

exec sudo /usr/local/sbin/pwc-cron update_hot_github_trending "$@"
