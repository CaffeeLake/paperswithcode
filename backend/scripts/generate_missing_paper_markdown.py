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
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
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
    r"(<img\b[^>]*\bsrc=[\"'])(?P<source>[^\"']+)([\"'][^>]*>)", re.IGNORECASE
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FORMAT_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
STATUS_SCHEMA_VERSION = 2
MAX_ATTEMPTS = int(os.environ.get("PWC_MARKDOWN_MAX_ATTEMPTS", "3"))
VLLM_SHUTDOWN_TIMEOUT_SECONDS = int(
    os.environ.get("PWC_MARKDOWN_VLLM_SHUTDOWN_TIMEOUT_SECONDS", "60")
)
_TERMINATION_REQUESTED = False


def request_termination(_signum: int, _frame: object) -> None:
    global _TERMINATION_REQUESTED
    _TERMINATION_REQUESTED = True


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


def _arxiv_version_candidates(version: str) -> list[str]:
    match = re.fullmatch(r"v([1-9][0-9]*)", version)
    if match is None:
        return [version]
    requested = int(match.group(1))
    lower_versions = range(min(requested - 1, 10), 0, -1)
    return [version, *(f"v{number}" for number in lower_versions)]


def download_pdf(arxiv_id: str, version: str) -> tuple[bytes, str]:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True
    ) as client:
        candidates = _arxiv_version_candidates(version)
        for index, candidate in enumerate(candidates):
            url = f"https://arxiv.org/pdf/{arxiv_id}{candidate}.pdf"
            response = client.get(url)
            if response.status_code == 404 and index + 1 < len(candidates):
                continue
            response.raise_for_status()
            data = response.content
            if not data.startswith(b"%PDF-") or len(data) > 150 * 1024 * 1024:
                raise ValueError("invalid_pdf")
            return data, candidate
    raise RuntimeError("arxiv_version_candidates_exhausted")


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
    assets: dict[str, bytes] = {}
    for path in output.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        data = path.read_bytes()
        existing = assets.get(path.name)
        if existing is not None and existing != data:
            raise ValueError(f"ambiguous_chandra_asset:{path.name}")
        assets[path.name] = data
    return markdown_path.read_text(encoding="utf-8"), assets


def canonicalize_assets(
    arxiv_id: str,
    body: str,
    assets: dict[str, bytes],
    *,
    allow_missing_images: bool = False,
) -> tuple[str, dict[str, bytes], list[str], list[str]]:
    """Validate images and replace Chandra-local references with public URLs."""
    source_to_url: dict[str, str] = {}
    canonical_assets: dict[str, bytes] = {}
    asset_keys: list[str] = []
    omitted_sources: list[str] = []
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
            if allow_missing_images:
                omitted_sources.append(source)
                return ""
            raise ValueError(f"missing_extracted_image:{source}")
        return f"{match.group(1)}{replacement}{match.group(3)}"

    rewritten = MARKDOWN_IMAGE.sub(replace, body)
    rewritten = HTML_IMAGE.sub(replace, rewritten)
    return (
        rewritten,
        canonical_assets,
        sorted(set(asset_keys)),
        sorted(set(omitted_sources)),
    )


def publish(
    entry: dict[str, object],
    body: str,
    assets: dict[str, bytes],
    content_root: Path,
    *,
    page_count: int | None = None,
    processed_pages: int | None = None,
    allow_missing_images: bool = False,
) -> dict:
    arxiv_id = str(entry["arxiv_id"])
    version = str(entry["version"])
    body, canonical_assets, asset_keys, omitted_sources = canonicalize_assets(
        arxiv_id,
        body,
        assets,
        allow_missing_images=allow_missing_images,
    )
    if omitted_sources:
        body = (
            f"> **Image note:** {len(omitted_sources)} generated image "
            f"reference{'s were' if len(omitted_sources) != 1 else ' was'} omitted "
            f"because Chandra did not produce a corresponding validated asset.\n\n"
            f"{body}"
        )
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
        "omitted_image_count": len(omitted_sources),
        "omitted_image_sources": omitted_sources,
        "asset_keys": asset_keys,
        "asset_sha256": {
            key: hashlib.sha256(canonical_assets[key]).hexdigest() for key in asset_keys
        },
        "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
    }


def process(
    entry: dict[str, object],
    content_root: Path,
    run_root: Path,
    *,
    allow_missing_images: bool = False,
) -> dict:
    from pypdf import PdfReader

    started = time.monotonic()
    arxiv_id = str(entry["arxiv_id"])
    version = str(entry["version"])
    output = content_root / str(entry["output_key"])
    if output.exists():
        return {"arxiv_id": arxiv_id, "status": "already_exists"}

    paper_dir = run_root / arxiv_id
    pdf_data, resolved_version = download_pdf(arxiv_id, version)
    page_count = len(PdfReader(BytesIO(pdf_data), strict=True).pages)
    processed_pages = min(page_count, MAX_PAGES)
    pdf_path = paper_dir / "paper.pdf"
    atomic_write(pdf_path, pdf_data)
    body, assets = run_chandra(pdf_path, paper_dir / "ocr", processed_pages)
    result = publish(
        {**entry, "version": resolved_version},
        body,
        assets,
        content_root,
        page_count=page_count,
        processed_pages=processed_pages,
        allow_missing_images=allow_missing_images,
    )
    return {
        **result,
        "requested_version": version,
        "resolved_version": resolved_version,
        "version_fallback_attempted": True,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(UTC).isoformat(),
    }


def _prior_status(content_root: Path, arxiv_id: str) -> dict:
    path = content_root / "_jobs" / "status" / f"{arxiv_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def should_omit_missing_images(prior: dict, attempt_count: int) -> bool:
    """Allow one full retry before publishing with phantom image refs omitted."""
    return attempt_count >= MAX_ATTEMPTS or (
        attempt_count >= 2 and prior.get("error_class") == "missing_extracted_image"
    )


def classify_failure(error: Exception, attempt_count: int) -> tuple[str, bool]:
    """Classify a paper failure without requiring scheduler string parsing."""
    message = str(error)
    error_class = type(error).__name__
    retryable = False
    if isinstance(error, httpx.TimeoutException):
        error_class, retryable = "arxiv_timeout", True
    elif isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        error_class = f"arxiv_http_{status}"
        retryable = status == 429 or status >= 500
    elif isinstance(error, subprocess.CalledProcessError):
        error_class, retryable = "chandra_subprocess_failure", True
    elif message.startswith("missing_extracted_image:"):
        error_class, retryable = "missing_extracted_image", True
    elif message.startswith(
        ("asset_verification_failed:", "markdown_verification_failed")
    ):
        error_class, retryable = "artifact_verification_io", True
    elif message.startswith("immutable_asset_conflict:"):
        error_class = "immutable_asset_conflict"
    elif message.startswith("ambiguous_chandra_asset:"):
        error_class = "ambiguous_chandra_asset"
    elif message in {"invalid_pdf", "invalid_chandra_output"}:
        error_class = message
        retryable = message == "invalid_chandra_output" and attempt_count < 2
    elif message in {
        "invalid_extracted_image",
        "unsupported_extracted_image",
        "image_too_large",
        "image_too_many_pixels",
        "invalid_markdown_size",
    }:
        error_class = message
    elif isinstance(error, OSError):
        error_class, retryable = "transient_io", True
    if attempt_count >= MAX_ATTEMPTS:
        retryable = False
    return error_class, retryable


def status_record(
    result: dict,
    *,
    prior: dict,
    error: Exception | None = None,
    attempted_at: datetime | None = None,
) -> dict:
    """Add retry metadata while retaining all legacy result fields."""
    observed_at = attempted_at or datetime.now(UTC)
    attempt_count = max(0, int(prior.get("attempt_count") or 0)) + 1
    retryable = False
    error_class = None
    next_retry_at = None
    if error is not None:
        error_class, retryable = classify_failure(error, attempt_count)
        if retryable:
            delay = timedelta(hours=min(24, 2 ** (attempt_count - 1)))
            next_retry_at = (observed_at + delay).isoformat()
    return {
        **result,
        "schema_version": STATUS_SCHEMA_VERSION,
        "attempt_count": attempt_count,
        "error_class": error_class,
        "retryable": retryable,
        "attempted_at": observed_at.isoformat(),
        "next_retry_at": next_retry_at,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
    }


def stop_vllm(process: subprocess.Popen[bytes] | None) -> str:
    if process is None:
        return "not_started"
    if process.poll() is not None:
        return "already_exited"
    process.terminate()
    try:
        process.wait(timeout=VLLM_SHUTDOWN_TIMEOUT_SECONDS)
        return "terminated"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=30)
            return "killed"
        except subprocess.TimeoutExpired:
            return "kill_timed_out"


def progress_payload(
    *,
    run_id: str,
    shard_id: str,
    total_papers: int,
    results: list[dict],
    status: str,
    started_at: str,
    fatal_error: str | None = None,
    termination_requested: bool = False,
    cleanup_state: str | None = None,
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
        "omitted_images": sum(
            int(item.get("omitted_image_count") or 0) for item in results
        ),
        "error_samples": [
            {
                "arxiv_id": item.get("arxiv_id"),
                "error": str(item.get("error") or "")[:500],
            }
            for item in failed[:5]
        ],
        "fatal_error": fatal_error,
        "termination_requested": termination_requested,
        "cleanup_state": cleanup_state,
        "paper_duration_p50_seconds": percentile_duration(results, 0.50),
        "paper_duration_p95_seconds": percentile_duration(results, 0.95),
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def percentile_duration(results: list[dict], percentile: float) -> float | None:
    values = sorted(
        float(item["duration_seconds"])
        for item in results
        if item.get("duration_seconds") is not None
    )
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile + 0.999)))
    return round(values[index], 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, default=Path("/content"))
    parser.add_argument("--stub-root", type=Path)
    parser.add_argument("--stub-delay-seconds", type=float, default=0)
    parser.add_argument(
        "--soft-deadline-seconds",
        type=int,
        default=int(os.environ.get("PWC_MARKDOWN_SOFT_DEADLINE_SECONDS", "40500")),
    )
    args = parser.parse_args()
    if args.soft_deadline_seconds < 0:
        parser.error("--soft-deadline-seconds must not be negative")

    global _TERMINATION_REQUESTED
    _TERMINATION_REQUESTED = False
    signal.signal(signal.SIGTERM, request_termination)
    deadline = time.monotonic() + args.soft_deadline_seconds

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
    cleanup_state = None
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
            if _TERMINATION_REQUESTED or time.monotonic() >= deadline:
                break
            prior = _prior_status(args.content_root, str(entry["arxiv_id"]))
            attempt_count = max(0, int(prior.get("attempt_count") or 0)) + 1
            allow_missing_images = should_omit_missing_images(prior, attempt_count)
            attempted_at = datetime.now(UTC)
            failure = None
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
                    started = time.monotonic()
                    result = publish(
                        entry,
                        body,
                        assets,
                        args.content_root,
                        allow_missing_images=allow_missing_images,
                    )
                    result["duration_seconds"] = round(time.monotonic() - started, 3)
                    if args.stub_delay_seconds:
                        time.sleep(args.stub_delay_seconds)
                else:
                    result = process(
                        entry,
                        args.content_root,
                        result_path.parent,
                        allow_missing_images=allow_missing_images,
                    )
            except Exception as error:  # noqa: BLE001 - isolate failures per paper
                failure = error
                result = {
                    "arxiv_id": entry["arxiv_id"],
                    "status": "failed",
                    "error": str(error)[:1000],
                    "requested_version": entry["version"],
                    "version_fallback_attempted": not bool(args.stub_root),
                }
            result = status_record(
                result,
                prior=prior,
                error=failure,
                attempted_at=attempted_at,
            )
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
        cleanup_state = stop_vllm(server)
        final_status = (
            "failed"
            if fatal_error
            else "completed"
            if len({item.get("arxiv_id") for item in results}) >= len(entries)
            else "partial"
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
                    termination_requested=_TERMINATION_REQUESTED,
                    cleanup_state=cleanup_state,
                ),
                sort_keys=True,
                indent=2,
            ).encode(),
        )


if __name__ == "__main__":
    main()
