"""Restartable vLLM worker for immutable title-and-abstract paper summaries."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from vllm import LLM, SamplingParams


SCHEMA_VERSION = "paper-summaries-v1"
INPUT_FORMAT_VERSION = "paper-summary-title-abstract-v1"
PROMPT_VERSION = "retrieval-summary-v10-source-aware"
SYSTEM_PROMPT = """You write factual retrieval summaries of research papers.
Use only the supplied title and abstract. Do not add outside knowledge, citations,
unsupported claims, or generic commentary. Return only the summary text."""
USER_PROMPT_TEMPLATE = """Write one concise {minimum_words}–120 word retrieval-oriented summary; aim for {target_words} words.
Preserve the paper's central problem, primary method or contribution, experimental
or deployment setting, and principal result when each is stated. Do not invent a
missing result. Use concrete technical terms that would help retrieve this paper.
Do not include a heading, citation, bullet list, or boilerplate such as \"this paper
presents\".

Title: {title}

Abstract: {abstract}"""
REPAIR_PROMPT_TEMPLATE = """Rewrite the draft as one factual 100–110 word summary.
It had {word_count} words and failed these checks: {validation_errors}.
Count the words before responding. Return only the corrected summary as one
paragraph. Retain only claims supported by the title and abstract. Do not output
the word count, analysis, self-correction, or a second draft.

Title: {title}

Abstract: {abstract}

Draft: {draft}"""
SHORT_REPAIR_PROMPT_TEMPLATE = """Rewrite the draft as exactly six complete sentences of 14–16 words each.
Use only the title and abstract. Map the sentences to the contribution,
participants, setting, collection method, annotation, and scope when applicable.
Redistribute or rephrase source details if a category is absent; never add a new
claim. Do not claim benefits, challenges, comparisons, exclusions, or intended
uses unless explicitly stated. Return one paragraph only; do not output a word
count, analysis, or self-correction.

Title: {title}

Abstract: {abstract}

Draft: {draft}"""
PROMPT_HASH = hashlib.sha256(
    (
        f"{PROMPT_VERSION}\0{SYSTEM_PROMPT}\0{USER_PROMPT_TEMPLATE}"
        f"\0{REPAIR_PROMPT_TEMPLATE}\0{SHORT_REPAIR_PROMPT_TEMPLATE}"
    ).encode("utf-8")
).hexdigest()
GENERATION_PARAMETERS = {
    "temperature": 0.0,
    "top_p": 1.0,
    "top_k": -1,
    "max_tokens": 192,
    "seed": 0,
    "thinking": False,
    "max_validation_attempts": 5,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def word_count(value: str) -> int:
    import re

    return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", value, re.UNICODE))


def summary_word_bounds(abstract: str) -> tuple[int, int]:
    source_words = word_count(abstract)
    if source_words >= 100:
        return 80, 120
    return min(80, max(30, math.ceil(0.75 * source_words))), 120


def validation_errors(value: str, *, abstract: str) -> list[str]:
    import re

    summary = value.strip()
    if not summary:
        return ["empty"]
    errors = []
    words = word_count(summary)
    minimum_words, maximum_words = summary_word_bounds(abstract)
    if words < minimum_words:
        errors.append("too_short")
    if words > maximum_words:
        errors.append("too_long")
    lowered = summary.casefold()
    if any(
        phrase in lowered
        for phrase in (
            "here is the summary",
            "here's the summary",
            "this paper presents",
            "the provided abstract",
            "as an ai language model",
            "i cannot",
        )
    ):
        errors.append("boilerplate")
    if "<think" in lowered or "</think" in lowered:
        errors.append("thinking_markup")
    if re.search(r"\[[0-9]+(?:\s*[-,]\s*[0-9]+)*\]", summary):
        errors.append("citation_like")
    if any(ord(character) < 32 and character not in "\n\t" for character in summary):
        errors.append("control_character")
    return errors


def strip_reasoning(value: str) -> str:
    text = value.strip()
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1].strip()
    return text


def render_prompt(tokenizer, record: dict, previous: dict | None = None) -> str:
    if previous is None:
        minimum_words, maximum_words = summary_word_bounds(record["abstract"])
        target_words = (
            "100–110"
            if minimum_words == 80
            else f"{minimum_words}–{min(maximum_words, minimum_words + 20)}"
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            minimum_words=minimum_words,
            target_words=target_words,
            title=record["title"],
            abstract=record["abstract"],
        )
    else:
        repair_template = (
            SHORT_REPAIR_PROMPT_TEMPLATE
            if "too_short" in previous["validation_errors"]
            else REPAIR_PROMPT_TEMPLATE
        )
        user_prompt = repair_template.format(
            word_count=word_count(previous["summary"]),
            validation_errors=", ".join(previous["validation_errors"]),
            title=record["title"],
            abstract=record["abstract"],
            draft=previous["summary"],
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def valid_marker(
    output_path: Path, marker_path: Path, rows: int, input_sha256: str
) -> dict | None:
    if not output_path.is_file() or not marker_path.is_file():
        return None
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        marker.get("rows") == rows
        and marker.get("input_sha256") == input_sha256
        and marker.get("sha256") == sha256_file(output_path)
    ):
        return marker
    return None


def write_jsonl_atomic(path: Path, rows: list[dict]) -> dict[str, object]:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    read_rows(temporary)
    temporary.replace(path)
    return {"path": path.name, "rows": len(rows), "sha256": sha256_file(path)}


def peak_vram_bytes() -> int:
    values = [torch.cuda.max_memory_reserved() if torch.cuda.is_available() else 0]
    try:
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
            int(line.strip()) * 1024 * 1024
            for line in output.splitlines()
            if line.strip()
        )
    except (OSError, ValueError):
        pass
    return max(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.92)
    args = parser.parse_args()
    source = json.loads((args.input / "manifest.json").read_text(encoding="utf-8"))
    for key, expected in (
        ("schema_version", SCHEMA_VERSION),
        ("input_format_version", INPUT_FORMAT_VERSION),
        ("prompt_version", PROMPT_VERSION),
        ("prompt_hash", PROMPT_HASH),
        ("generation_parameters", GENERATION_PARAMETERS),
    ):
        if source.get(key) != expected:
            raise ValueError(f"Input manifest mismatch for {key}")
    for shard in source["shards"]:
        if sha256_file(args.input / shard["path"]) != shard["sha256"]:
            raise ValueError(f"Input checksum mismatch: {shard['path']}")

    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    llm = LLM(
        model=args.model,
        revision=args.revision,
        dtype="bfloat16",
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
        seed=GENERATION_PARAMETERS["seed"],
        trust_remote_code=False,
        language_model_only=True,
    )
    startup_seconds = time.monotonic() - started
    tokenizer = llm.get_tokenizer()
    sampling = SamplingParams(
        temperature=GENERATION_PARAMETERS["temperature"],
        top_p=GENERATION_PARAMETERS["top_p"],
        top_k=GENERATION_PARAMETERS["top_k"],
        max_tokens=GENERATION_PARAMETERS["max_tokens"],
        seed=GENERATION_PARAMETERS["seed"],
    )
    output_shards: list[dict] = []
    seen: set[int] = set()
    valid_count = invalid_count = error_count = output_tokens = 0
    for index, shard in enumerate(source["shards"]):
        input_path = args.input / shard["path"]
        records = read_rows(input_path)
        output_path = args.output / f"summaries-{index:05d}.jsonl"
        marker_path = output_path.with_suffix(".complete.json")
        marker = valid_marker(output_path, marker_path, len(records), shard["sha256"])
        if marker:
            rows = read_rows(output_path)
            output_shards.append(marker)
        else:
            states = [
                {
                    "summary": "",
                    "validation_errors": ["empty"],
                    "error": None,
                    "output_tokens": 0,
                    "attempts": 0,
                }
                for _ in records
            ]
            pending = list(range(len(records)))
            for attempt in range(
                1, GENERATION_PARAMETERS["max_validation_attempts"] + 1
            ):
                prompts = [
                    render_prompt(
                        tokenizer,
                        records[index],
                        states[index] if attempt > 1 else None,
                    )
                    for index in pending
                ]
                try:
                    results = llm.generate(prompts, sampling, use_tqdm=True)
                except Exception as exc:
                    batch_error = f"{type(exc).__name__}: {exc}"
                    for index in pending:
                        states[index]["error"] = batch_error
                        states[index]["attempts"] = attempt
                    break
                next_pending = []
                for index, result in zip(pending, results, strict=True):
                    try:
                        choice = result.outputs[0]
                        summary = strip_reasoning(choice.text)
                        states[index] = {
                            "summary": summary,
                            "validation_errors": validation_errors(
                                summary, abstract=records[index]["abstract"]
                            ),
                            "error": None,
                            "output_tokens": states[index]["output_tokens"]
                            + len(choice.token_ids),
                            "attempts": attempt,
                        }
                    except Exception as exc:
                        states[index]["error"] = f"{type(exc).__name__}: {exc}"
                        states[index]["attempts"] = attempt
                    if states[index]["validation_errors"] or states[index]["error"]:
                        next_pending.append(index)
                pending = next_pending
                if not pending:
                    break
            rows = []
            for record, state in zip(records, states, strict=True):
                minimum_words, maximum_words = summary_word_bounds(record["abstract"])
                rows.append(
                    {
                        "paper_id": record["paper_id"],
                        "arxiv_id": record["arxiv_id"],
                        "paper_identifier": record["paper_identifier"],
                        "input_hash": record["input_hash"],
                        "summary": state["summary"],
                        "model": args.model,
                        "revision": args.revision,
                        "prompt_version": PROMPT_VERSION,
                        "prompt_hash": PROMPT_HASH,
                        "generation_parameters": GENERATION_PARAMETERS,
                        "validation_status": (
                            "valid"
                            if not state["validation_errors"] and not state["error"]
                            else "invalid"
                        ),
                        "validation_errors": state["validation_errors"],
                        "error": state["error"],
                        "output_tokens": state["output_tokens"],
                        "generation_attempts": state["attempts"],
                        "source_abstract_word_count": word_count(record["abstract"]),
                        "effective_min_words": minimum_words,
                        "effective_max_words": maximum_words,
                    }
                )
            marker = write_jsonl_atomic(output_path, rows)
            marker["input_sha256"] = shard["sha256"]
            marker_tmp = marker_path.with_suffix(marker_path.suffix + ".tmp")
            marker_tmp.write_text(
                json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8"
            )
            marker_tmp.replace(marker_path)
            output_shards.append(marker)
        for row in rows:
            paper_id = int(row["paper_id"])
            if paper_id in seen:
                raise ValueError(f"Duplicate paper ID: {paper_id}")
            seen.add(paper_id)
            valid_count += row["validation_status"] == "valid"
            invalid_count += row["validation_status"] != "valid"
            error_count += bool(row.get("error"))
            output_tokens += int(row.get("output_tokens", 0))
    if len(seen) != source["row_count"]:
        raise ValueError("Output coverage differs from source manifest")
    duration_seconds = time.monotonic() - started
    final = {
        **{
            key: source[key]
            for key in (
                "schema_version",
                "run_id",
                "input_format_version",
                "prompt_version",
                "prompt_hash",
                "generation_parameters",
                "corpus_snapshot",
                "snapshot_time",
                "latest_paper_count",
                "eligible_paper_count",
                "excluded_missing_title_or_abstract",
                "row_count",
                "ordered_paper_ids_sha256",
            )
        },
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "revision": args.revision,
        "hardware": platform.platform(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "peak_vram_bytes": peak_vram_bytes(),
        "startup_seconds": startup_seconds,
        "duration_seconds": duration_seconds,
        "papers_per_second": len(seen) / duration_seconds if duration_seconds else None,
        "output_tokens": output_tokens,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
        "packages": {
            "vllm": importlib.metadata.version("vllm"),
            "torch": torch.__version__,
        },
        "shards": output_shards,
    }
    temporary = args.output / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output / "manifest.json")
    print(json.dumps(final, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
