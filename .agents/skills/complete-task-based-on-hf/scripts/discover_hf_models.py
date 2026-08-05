#!/usr/bin/env python3
"""Fetch and merge live Hugging Face model popularity rankings via the hf CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
EXPAND = (
    "author,downloads,downloadsAllTime,likes,trendingScore,createdAt,"
    "lastModified,tags,baseModels,pipeline_tag"
)
QUANT_MARKERS = ("gguf", "onnx", "awq", "gptq", "fp8", "int4", "quantized")


def fetch(pipeline_tag: str, sort: str, limit: int) -> list[dict]:
    command = [
        "uv",
        "run",
        "hf",
        "models",
        "list",
        "--pipeline-tag",
        pipeline_tag,
        "--sort",
        sort,
        "--limit",
        str(limit),
        "--expand",
        EXPAND,
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def classify(model: dict) -> str:
    tags = [str(tag).lower() for tag in model.get("tags") or []]
    model_id = str(model["id"]).lower()
    if any("base_model:quantized:" in tag for tag in tags) or any(
        marker in model_id for marker in QUANT_MARKERS
    ):
        return "quantized-or-converted"
    if any("base_model:adapter:" in tag for tag in tags):
        return "adapter"
    if any("base_model:finetune:" in tag for tag in tags):
        return "finetune"
    return "candidate-original"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-tag", required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    trending = fetch(args.pipeline_tag, "trending_score", args.limit)
    downloads = fetch(args.pipeline_tag, "downloads", args.limit)
    merged: dict[str, dict] = {}

    for ranking_name, rows in (("trending", trending), ("downloads", downloads)):
        for rank, model in enumerate(rows, start=1):
            entry = merged.setdefault(
                model["id"],
                {
                    **model,
                    "trending_rank": None,
                    "downloads_rank": None,
                },
            )
            entry[f"{ranking_name}_rank"] = rank

    candidates = []
    for model in merged.values():
        tags = [str(tag) for tag in model.get("tags") or []]
        model["arxiv_ids"] = [
            tag.split(":", 1)[1] for tag in tags if tag.startswith("arxiv:")
        ]
        model["candidate_kind"] = classify(model)
        candidates.append(model)

    candidates.sort(
        key=lambda model: (
            model["trending_rank"] is None,
            model["trending_rank"] or 10**9,
            model["downloads_rank"] or 10**9,
        )
    )
    output = {
        "pipeline_tag": args.pipeline_tag,
        "limit_per_sort": args.limit,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "exact_repo_count": len(candidates),
        "candidates": candidates,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
