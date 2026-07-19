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

# The official vllm/vllm-openai image already contains a CUDA-matched vLLM
# installation. Installing another wheel here can replace it with an ABI- or
# toolkit-incompatible build.
exec python3 "$worker" \
  --input "$input_dir" \
  --output "$output_dir" \
  --model "$model" \
  --revision "$revision" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.92
