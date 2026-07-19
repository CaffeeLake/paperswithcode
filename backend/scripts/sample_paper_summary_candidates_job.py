"""Generate a bounded, seeded candidate set for one difficult paper summary.

This worker is intentionally separate from the frozen greedy comparison worker.
It records every sampled candidate and emits the first mechanically valid one in
the standard single-row summary artifact shape for later human fidelity review.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from vllm import LLM, SamplingParams


PROMPT_VERSION = "retrieval-summary-sampling-repair-v1"
SYSTEM_PROMPT = """You write factual retrieval summaries of research papers.
Use only the supplied title and abstract. Return only the summary paragraph."""
USER_PROMPT_TEMPLATE = """Write one factual 80-100 word retrieval summary using only the title and abstract.
Preserve every concrete source detail, including the contribution, participant count,
setting, sensor locations and type, annotation method, and activity count. You may
rephrase source details for clarity, but do not infer motivations, benefits, uses,
results, comparisons, exclusions, or properties not stated in the source. Do not
include headings, citations, boilerplate, analysis, alternatives, or word-count
commentary. Return exactly one paragraph.

Title: {title}

Abstract: {abstract}"""
PROMPT_HASH = hashlib.sha256(
    f"{PROMPT_VERSION}\0{SYSTEM_PROMPT}\0{USER_PROMPT_TEMPLATE}".encode("utf-8")
).hexdigest()
SEEDS = list(range(24001, 24025))
GENERATION_PARAMETERS = {
    "temperature": 0.6,
    "top_p": 0.9,
    "top_k": -1,
    "max_tokens": 160,
    "thinking": False,
    "seeds": SEEDS,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def write_jsonl(path: Path, rows: list[dict]) -> str:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)
    return sha256_file(path)


def word_count(value: str) -> int:
    import re

    return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", value, re.UNICODE))


def validation_errors(value: str) -> list[str]:
    import re

    summary = value.strip()
    errors = []
    if not summary:
        return ["empty"]
    words = word_count(summary)
    if words < 80:
        errors.append("too_short")
    if words > 100:
        errors.append("too_long")
    lowered = summary.casefold()
    if any(
        phrase in lowered
        for phrase in (
            "here is the summary",
            "here's the summary",
            "this paper presents",
            "the provided abstract",
            "word count",
            "words long",
            "as an ai language model",
            "i cannot",
        )
    ):
        errors.append("boilerplate")
    if "<think" in lowered or "</think" in lowered:
        errors.append("thinking_markup")
    if re.search(r"\[[0-9]+(?:\s*[-,]\s*[0-9]+)*\]", summary):
        errors.append("citation_like")
    if "\n" in summary:
        errors.append("multiple_paragraphs")
    if any(ord(character) < 32 and character not in "\n\t" for character in summary):
        errors.append("control_character")
    return errors


def peak_vram_bytes() -> int:
    values = [torch.cuda.max_memory_reserved() if torch.cuda.is_available() else 0]
    output = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    ).stdout
    values.extend(
        int(line.strip()) * 1024 * 1024 for line in output.splitlines() if line.strip()
    )
    return max(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--paper-id", type=int, required=True)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.93)
    args = parser.parse_args()

    source = json.loads((args.input / "manifest.json").read_text(encoding="utf-8"))
    input_rows = []
    for shard in source["shards"]:
        path = args.input / shard["path"]
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"Input checksum mismatch: {path}")
        input_rows.extend(read_jsonl(path))
    matches = [row for row in input_rows if int(row["paper_id"]) == args.paper_id]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one row for paper {args.paper_id}, got {len(matches)}"
        )
    record = matches[0]
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty output: {args.output}")

    started = time.monotonic()
    llm = LLM(
        model=args.model,
        revision=args.revision,
        dtype="bfloat16",
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
        seed=SEEDS[0],
        trust_remote_code=False,
        language_model_only=True,
    )
    startup_seconds = time.monotonic() - started
    tokenizer = llm.get_tokenizer()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(**record)},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    candidates = []
    for seed in SEEDS:
        sampling = SamplingParams(
            temperature=GENERATION_PARAMETERS["temperature"],
            top_p=GENERATION_PARAMETERS["top_p"],
            top_k=GENERATION_PARAMETERS["top_k"],
            max_tokens=GENERATION_PARAMETERS["max_tokens"],
            seed=seed,
        )
        result = llm.generate([prompt], sampling, use_tqdm=True)[0].outputs[0]
        summary = result.text.strip()
        errors = validation_errors(summary)
        candidates.append(
            {
                "candidate_index": len(candidates),
                "seed": seed,
                "summary": summary,
                "word_count": word_count(summary),
                "validation_status": "valid" if not errors else "invalid",
                "validation_errors": errors,
                "output_tokens": len(result.token_ids),
            }
        )

    valid = [
        candidate
        for candidate in candidates
        if candidate["validation_status"] == "valid"
    ]
    selected = valid[0] if valid else candidates[0]
    selected_row = {
        "paper_id": record["paper_id"],
        "arxiv_id": record["arxiv_id"],
        "paper_identifier": record["paper_identifier"],
        "input_hash": record["input_hash"],
        "summary": selected["summary"],
        "model": args.model,
        "revision": args.revision,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH,
        "generation_parameters": GENERATION_PARAMETERS,
        "selected_seed": selected["seed"],
        "selected_candidate_index": selected["candidate_index"],
        "selection_policy": "first-mechanically-valid-seed-order-for-human-review-v1",
        "validation_status": selected["validation_status"],
        "validation_errors": selected["validation_errors"],
        "error": None,
        "output_tokens": selected["output_tokens"],
        "generation_attempts": len(candidates),
    }
    candidates_path = args.output / "sampled-candidates.jsonl"
    candidates_sha256 = write_jsonl(candidates_path, candidates)
    output_path = args.output / "summaries-00000.jsonl"
    output_sha256 = write_jsonl(output_path, [selected_row])
    duration_seconds = time.monotonic() - started
    manifest = {
        "schema_version": "paper-summaries-v1",
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "run_id": source["run_id"],
        "corpus_snapshot": source["corpus_snapshot"],
        "snapshot_time": source["snapshot_time"],
        "row_count": 1,
        "valid_count": int(selected_row["validation_status"] == "valid"),
        "invalid_count": int(selected_row["validation_status"] != "valid"),
        "error_count": 0,
        "ordered_paper_ids_sha256": source["ordered_paper_ids_sha256"],
        "input_shard_sha256": source["shards"][0]["sha256"],
        "model": args.model,
        "revision": args.revision,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH,
        "generation_parameters": GENERATION_PARAMETERS,
        "selection_policy": selected_row["selection_policy"],
        "selected_seed": selected["seed"],
        "selected_candidate_index": selected["candidate_index"],
        "candidate_count": len(candidates),
        "mechanically_valid_candidate_count": len(valid),
        "candidates": {
            "path": candidates_path.name,
            "rows": len(candidates),
            "sha256": candidates_sha256,
        },
        "hardware": platform.platform(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "peak_vram_bytes": peak_vram_bytes(),
        "startup_seconds": startup_seconds,
        "duration_seconds": duration_seconds,
        "packages": {
            "vllm": importlib.metadata.version("vllm"),
            "torch": torch.__version__,
        },
        "shards": [{"path": output_path.name, "rows": 1, "sha256": output_sha256}],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
