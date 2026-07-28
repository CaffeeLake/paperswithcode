# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "chandra-ocr==0.2.0",
#   "httpx>=0.28.1",
#   "pillow>=11.0.0",
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
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

MODEL_ID = os.environ.get("PWC_MARKDOWN_MODEL_ID", "datalab-to/chandra-ocr-2")
MODEL_REVISION = os.environ.get(
    "PWC_MARKDOWN_MODEL_REVISION",
    "af93b47dba1b47b6640c86ccf487ed2260ab9a09",
)
MAX_PAGES = int(os.environ.get("PWC_MARKDOWN_MAX_PAGES", "30"))
USER_AGENT = "paperswithcode-paper-markdown/1.0 (https://paperswithcode.co)"
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
MARKDOWN_IMAGE = re.compile(r"(!\[[^\]]*\]\()(?P<source>[^)\s]+)(\))")
HTML_IMAGE = re.compile(
    r"(<img\b[^>]*\bsrc=[\"'])(?P<source>[^\"']+)([\"'])", re.IGNORECASE
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FORMAT_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


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


def run_chandra(pdf: Path, output: Path, pages: int) -> tuple[str, dict[str, bytes]]:
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
            f"0-{pages - 1}",
            "--max-output-tokens",
            "12384",
            "--include-images",
            "--no-html",
        ],
        env=env,
        check=True,
    )
    markdown_files = list(output.rglob("*.md"))
    if len(markdown_files) != 1:
        raise ValueError("invalid_chandra_output")
    markdown_path = markdown_files[0]
    assets = {
        path.name: path.read_bytes()
        for path in markdown_path.parent.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }
    return markdown_path.read_text(encoding="utf-8"), assets


def canonicalize_assets(
    arxiv_id: str, body: str, assets: dict[str, bytes]
) -> tuple[str, dict[str, bytes], list[str]]:
    """Validate images and replace Chandra-local references with public URLs."""
    source_to_url: dict[str, str] = {}
    canonical_assets: dict[str, bytes] = {}
    asset_keys: list[str] = []
    for source_name, data in sorted(assets.items()):
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image_too_large")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image_too_many_pixels")
                image.verify()
                extension = FORMAT_EXTENSIONS.get(image.format or "")
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("invalid_extracted_image") from error
        if extension is None:
            raise ValueError("unsupported_extracted_image")
        filename = f"{hashlib.sha256(data).hexdigest()[:16]}{extension}"
        key = f"{arxiv_id[:4]}/{arxiv_id}/images/{filename}"
        url = f"https://paperswithcode.co/paper-assets/{key}"
        source_to_url[Path(source_name).name] = url
        canonical_assets[key] = data
        asset_keys.append(key)

    def replace(match: re.Match[str]) -> str:
        source = match.group("source")
        if source.startswith(("https://", "http://", "data:")):
            return match.group(0)
        replacement = source_to_url.get(Path(source).name)
        if replacement is None:
            raise ValueError(f"missing_extracted_image:{source}")
        return f"{match.group(1)}{replacement}{match.group(3)}"

    rewritten = MARKDOWN_IMAGE.sub(replace, body)
    rewritten = HTML_IMAGE.sub(replace, rewritten)
    return rewritten, canonical_assets, sorted(set(asset_keys))


def publish(
    entry: dict[str, object],
    body: str,
    assets: dict[str, bytes],
    content_root: Path,
    *,
    page_count: int | None = None,
    processed_pages: int | None = None,
) -> dict:
    arxiv_id = str(entry["arxiv_id"])
    version = str(entry["version"])
    body, canonical_assets, asset_keys = canonicalize_assets(arxiv_id, body, assets)
    if page_count and processed_pages and page_count > processed_pages:
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

    for key, data in canonical_assets.items():
        destination = content_root / key
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"immutable_asset_conflict:{key}")
        if not destination.exists():
            atomic_write(destination, data)
        if destination.read_bytes() != data:
            raise ValueError(f"asset_verification_failed:{key}")

    output = content_root / str(entry["output_key"])
    atomic_write(output, markdown)
    if output.read_bytes() != markdown:
        raise ValueError("markdown_verification_failed")
    return {
        "arxiv_id": arxiv_id,
        "status": "succeeded",
        "page_count": page_count,
        "processed_page_count": processed_pages,
        "truncated": bool(
            page_count and processed_pages and page_count > processed_pages
        ),
        "image_count": len(asset_keys),
        "asset_keys": asset_keys,
        "asset_sha256": {
            key: hashlib.sha256(canonical_assets[key]).hexdigest() for key in asset_keys
        },
        "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
    }


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
    body, assets = run_chandra(pdf_path, paper_dir / "ocr", processed_pages)
    result = publish(
        entry,
        body,
        assets,
        content_root,
        page_count=page_count,
        processed_pages=processed_pages,
    )
    return {
        **result,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(UTC).isoformat(),
    }


def progress_payload(
    *,
    run_id: str,
    shard_id: str,
    total_papers: int,
    results: list[dict],
    status: str,
    started_at: str,
    fatal_error: str | None = None,
) -> dict:
    succeeded = [item for item in results if item.get("status") == "succeeded"]
    failed = [item for item in results if item.get("status") == "failed"]
    already_existed = [
        item for item in results if item.get("status") == "already_exists"
    ]
    return {
        "run_id": run_id,
        "shard_id": shard_id,
        "hf_job_id": os.environ.get("JOB_ID"),
        "status": status,
        "total_papers": total_papers,
        "processed_papers": len(results),
        "succeeded_papers": len(succeeded),
        "failed_papers": len(failed),
        "already_existed_papers": len(already_existed),
        "extracted_images": sum(int(item.get("image_count") or 0) for item in results),
        "error_samples": [
            {
                "arxiv_id": item.get("arxiv_id"),
                "error": str(item.get("error") or "")[:500],
            }
            for item in failed[:5]
        ],
        "fatal_error": fatal_error,
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
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
    progress_path = (
        args.content_root / "_jobs" / "progress" / run_id / f"{shard_id}.json"
    )
    completed: dict[str, dict] = {}
    if result_path.exists():
        completed = {
            item["arxiv_id"]: item
            for item in map(json.loads, result_path.read_text().splitlines())
        }

    started_at = datetime.now(UTC).isoformat()
    results = list(completed.values())
    server = None
    fatal_error = None
    atomic_write(
        progress_path,
        json.dumps(
            progress_payload(
                run_id=run_id,
                shard_id=shard_id,
                total_papers=len(entries),
                results=results,
                status="starting",
                started_at=started_at,
            ),
            sort_keys=True,
            indent=2,
        ).encode(),
    )
    try:
        if not args.stub_root:
            server = start_vllm()
        atomic_write(
            progress_path,
            json.dumps(
                progress_payload(
                    run_id=run_id,
                    shard_id=shard_id,
                    total_papers=len(entries),
                    results=results,
                    status="running",
                    started_at=started_at,
                ),
                sort_keys=True,
                indent=2,
            ).encode(),
        )
        for entry in entries:
            if entry["arxiv_id"] in completed:
                continue
            try:
                if args.stub_root:
                    body = (args.stub_root / f"{entry['arxiv_id']}.md").read_text(
                        encoding="utf-8"
                    )
                    asset_dir = args.stub_root / str(entry["arxiv_id"])
                    assets = (
                        {
                            path.name: path.read_bytes()
                            for path in asset_dir.iterdir()
                            if path.is_file()
                        }
                        if asset_dir.exists()
                        else {}
                    )
                    result = publish(entry, body, assets, args.content_root)
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
            atomic_write(
                progress_path,
                json.dumps(
                    progress_payload(
                        run_id=run_id,
                        shard_id=shard_id,
                        total_papers=len(entries),
                        results=results,
                        status="running",
                        started_at=started_at,
                    ),
                    sort_keys=True,
                    indent=2,
                ).encode(),
            )
    except Exception as error:
        fatal_error = str(error)[:1000]
        raise
    finally:
        if server is not None:
            server.terminate()
        final_status = (
            "failed"
            if fatal_error
            else "completed"
            if len(results) >= len(entries)
            else "stopped"
        )
        atomic_write(
            progress_path,
            json.dumps(
                progress_payload(
                    run_id=run_id,
                    shard_id=shard_id,
                    total_papers=len(entries),
                    results=results,
                    status=final_status,
                    started_at=started_at,
                    fatal_error=fatal_error,
                ),
                sort_keys=True,
                indent=2,
            ).encode(),
        )


if __name__ == "__main__":
    main()
