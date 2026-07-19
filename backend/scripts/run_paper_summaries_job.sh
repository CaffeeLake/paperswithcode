#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 5 ]]; then
  echo "usage: run_paper_summaries_job.sh WORKER INPUT OUTPUT MODEL REVISION" >&2
  exit 2
fi

worker="$1"
input_dir="$2"
output_dir="$3"
model="$4"
revision="$5"

uv pip install --system vllm --torch-backend=auto \
  --extra-index-url https://wheels.vllm.ai/nightly

python "$worker" \
  --input "$input_dir" \
  --output "$output_dir" \
  --model "$model" \
  --revision "$revision" \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.92
