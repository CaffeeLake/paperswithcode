#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: $0 WORKER INPUT OUTPUT MODEL REVISION PAPER_ID" >&2
  exit 2
fi

exec python3 "$1" \
  --input "$2" \
  --output "$3" \
  --model "$4" \
  --revision "$5" \
  --paper-id "$6" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.93
