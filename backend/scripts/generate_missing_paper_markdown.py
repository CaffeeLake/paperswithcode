# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "chandra-ocr==0.2.0",
#   "httpx>=0.28.1",
#   "pypdf>=5.0.0",
#   "vllm==0.17.0",
# ]
# ///
"""Generate missing paper Markdown with Chandra OCR 2 on an HF Job.

The content bucket is mounted at ``/content``. A manifest is immutable, each
paper is checkpointed independently, and canonical Markdown is written last.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx

MODEL_ID = os.environ.get("PWC_MARKDOWN_MODEL_ID", "datalab-to/chandra-ocr-2")
MODEL_REVISION = os.environ.get(
    "PWC_MARKDOWN_MODEL_REVISION",
    "af93b47dba1b47b6640c86ccf487ed2260ab9a09",
)
MAX_PAGES = int(os.environ.get("PWC_MARKDOWN_MAX_PAGES", "30"))
USER_AGENT = "paperswithcode-paper-markdown/1.0 (https://paperswithcode.co)"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def wait_for_vllm(process: subprocess.Popen[bytes], timeout: int = 900) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("vLLM exited during startup")
        try:
            if httpx.get("http://127.0.0.1:8000/health", timeout=2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise TimeoutError("vLLM startup timed out")


def start_vllm() -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            MODEL_ID,
            "--revision",
            MODEL_REVISION,
            "--served-model-name",
            "chandra",
            "--max-model-len",
            "18000",
            "--gpu-memory-utilization",
            "0.85",
            "--port",
            "8000",
            "--trust-remote-code",
            "--dtype",
            "bfloat16",
            "--max-num-seqs",
            "32",
            "--max_num_batched_tokens",
            "4096",
            "--enable-prefix-caching",
            "--mm-processor-kwargs",
            '{"min_pixels":3136,"max_pixels":6291456}',
            "--api-key",
            "EMPTY",
            "--no-enable-log-requests",
        ]
    )
    wait_for_vllm(process)
    return process


def download_pdf(arxiv_id: str, version: str) -> bytes:
    url = f"https://arxiv.org/pdf/{arxiv_id}{version}.pdf"
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True
    ) as client:
        response = client.get(url)
        response.raise_for_status()
    data = response.content
    if not data.startswith(b"%PDF-") or len(data) > 150 * 1024 * 1024:
        raise ValueError("invalid_pdf")
    return data


def run_chandra(pdf: Path, output: Path, pages: int) -> str:
    output.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "VLLM_API_BASE": "http://127.0.0.1:8000/v1",
        "VLLM_MODEL_NAME": "chandra",
        "VLLM_API_KEY": "EMPTY",
    }
    subprocess.run(
        [
            "chandra",
            str(pdf),
            str(output),
            "--method",
            "vllm",
            "--page-range",
            f"1-{pages}",
            "--max-output-tokens",
            "12384",
        ],
        env=env,
        check=True,
    )
    markdown_files = list(output.rglob("*.md"))
    if len(markdown_files) != 1:
        raise ValueError("invalid_chandra_output")
    return markdown_files[0].read_text(encoding="utf-8")


def process(entry: dict[str, object], content_root: Path, run_root: Path) -> dict:
    from pypdf import PdfReader

    started = time.monotonic()
    arxiv_id = str(entry["arxiv_id"])
    version = str(entry["version"])
    output = content_root / str(entry["output_key"])
    if output.exists():
        return {"arxiv_id": arxiv_id, "status": "already_exists"}

    paper_dir = run_root / arxiv_id
    pdf_data = download_pdf(arxiv_id, version)
    page_count = len(PdfReader(BytesIO(pdf_data), strict=True).pages)
    processed_pages = min(page_count, MAX_PAGES)
    pdf_path = paper_dir / "paper.pdf"
    atomic_write(pdf_path, pdf_data)
    body = run_chandra(pdf_path, paper_dir / "ocr", processed_pages)
    if page_count > processed_pages:
        body = (
            f"> **Truncated rendition:** This Markdown contains the first "
            f"{processed_pages} of {page_count} pages. Read the complete paper "
            f"at https://arxiv.org/pdf/{arxiv_id}{version}.pdf.\n\n{body}"
        )
    markdown = (
        f"Title: {str(entry['title']).strip()}\n\n"
        f"URL Source: https://arxiv.org/abs/{arxiv_id}{version}\n\n"
        f"Markdown Content:\n\n{body.strip()}\n"
    ).encode()
    if len(markdown) < 120 or len(markdown) > 64 * 1024 * 1024:
        raise ValueError("invalid_markdown_size")
    atomic_write(output, markdown)
    return {
        "arxiv_id": arxiv_id,
        "status": "succeeded",
        "page_count": page_count,
        "processed_page_count": processed_pages,
        "truncated": page_count > processed_pages,
        "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, default=Path("/content"))
    parser.add_argument("--stub-root", type=Path)
    args = parser.parse_args()

    entries = [
        json.loads(line)
        for line in args.manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_id = args.manifest.parent.name
    shard_id = args.manifest.stem
    result_path = args.content_root / "_jobs" / "results" / run_id / f"{shard_id}.jsonl"
    completed: dict[str, dict] = {}
    if result_path.exists():
        completed = {
            item["arxiv_id"]: item
            for item in map(json.loads, result_path.read_text().splitlines())
        }

    server = None if args.stub_root else start_vllm()
    results = list(completed.values())
    try:
        for entry in entries:
            if entry["arxiv_id"] in completed:
                continue
            try:
                if args.stub_root:
                    body = (args.stub_root / f"{entry['arxiv_id']}.md").read_text(
                        encoding="utf-8"
                    )
                    markdown = (
                        f"Title: {entry['title']}\n\n"
                        f"URL Source: https://arxiv.org/abs/"
                        f"{entry['arxiv_id']}{entry['version']}\n\n"
                        f"Markdown Content:\n\n{body}\n"
                    ).encode()
                    atomic_write(args.content_root / entry["output_key"], markdown)
                    result = {
                        "arxiv_id": entry["arxiv_id"],
                        "status": "succeeded",
                    }
                else:
                    result = process(entry, args.content_root, result_path.parent)
            except Exception as error:  # noqa: BLE001 - isolate failures per paper
                result = {
                    "arxiv_id": entry["arxiv_id"],
                    "status": "failed",
                    "error": str(error)[:1000],
                }
            results.append(result)
            atomic_write(
                args.content_root / "_jobs" / "status" / f"{entry['arxiv_id']}.json",
                json.dumps(result, sort_keys=True, indent=2).encode(),
            )
            atomic_write(
                result_path,
                (
                    "\n".join(json.dumps(item, sort_keys=True) for item in results)
                    + "\n"
                ).encode(),
            )
    finally:
        if server is not None:
            server.terminate()


if __name__ == "__main__":
    main()
