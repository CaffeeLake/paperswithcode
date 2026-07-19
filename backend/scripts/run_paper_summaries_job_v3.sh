#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 5 ]]; then
  echo "usage: $0 WORKER INPUT OUTPUT MODEL REVISION" >&2
  exit 2
fi

worker="$1"
input_dir="$2"
output_dir="$3"
model="$4"
revision="$5"

# Gemma 4 E4B measured 0.13 GiB of KV cache at 0.92 utilization while
# requiring 0.22 GiB for the fixed 4096-token context. On a 24 GiB L4,
# increasing utilization by 0.01 supplies sufficient bounded headroom.
exec python3 "$worker" \
  --input "$input_dir" \
  --output "$output_dir" \
  --model "$model" \
  --revision "$revision" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.93
