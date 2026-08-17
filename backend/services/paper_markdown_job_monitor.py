"""Cached monitoring for Chandra paper-Markdown Hugging Face Jobs."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from huggingface_hub import HfApi, HfFileSystem
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

from backend.config import Settings, get_settings
from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_snapshot,
)

_RUN_ID = re.compile(r"^(?:backfill|live)-\d{8}T\d{6}-[0-9a-f]{8}$")
_SHARD_ID = re.compile(r"^\d{5}$")
_JOB_STAGES = [
    "SCHEDULING",
    "RUNNING",
    "COMPLETED",
    "ERROR",
    "CANCELED",
]
_CACHE_SECONDS = 20
_CACHE_LOCK = threading.Lock()
_CACHE: tuple[float, dict[str, Any]] | None = None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stage(job: object) -> str:
    status = getattr(job, "status", None)
    stage = getattr(status, "stage", status)
    return str(getattr(stage, "value", stage) or "UNKNOWN").upper()


def _hardware(job: object) -> str | None:
    flavor = getattr(job, "flavor", None)
    if flavor is None:
        return None
    return str(getattr(flavor, "name", None) or flavor)


def _read_progress(
    filesystem: HfFileSystem,
    settings: Settings,
    run_id: str | None,
    shard_id: str | None,
) -> dict[str, Any] | None:
    if not run_id or not shard_id:
        return None
    if not _RUN_ID.fullmatch(run_id) or not _SHARD_ID.fullmatch(shard_id):
        return None

    path = (
        f"hf://buckets/{settings.paper_markdown_hf_bucket_id}/"
        f"_jobs/progress/{run_id}/{shard_id}.json"
    )
    try:
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(64 * 1024 + 1)
    except (EntryNotFoundError, FileNotFoundError, HfHubHTTPError):
        return None
    if len(raw) > 64 * 1024:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    integer_fields = (
        "total_papers",
        "processed_papers",
        "succeeded_papers",
        "failed_papers",
        "already_existed_papers",
        "extracted_images",
    )
    progress: dict[str, Any] = {
        key: max(0, int(payload.get(key) or 0)) for key in integer_fields
    }
    progress.update(
        {
            "status": str(payload.get("status") or "unknown")[:32],
            "updated_at": str(payload.get("updated_at") or "")[:64] or None,
            "started_at": str(payload.get("started_at") or "")[:64] or None,
            "fatal_error": str(payload.get("fatal_error") or "")[:1000] or None,
            "error_samples": [
                {
                    "arxiv_id": str(item.get("arxiv_id") or "")[:32],
                    "error": str(item.get("error") or "")[:500],
                }
                for item in (payload.get("error_samples") or [])[:5]
                if isinstance(item, dict)
            ],
        }
    )
    return progress


def _fetch(settings: Settings) -> dict[str, Any]:
    if not settings.hf_token:
        return {
            "available": False,
            "namespace": settings.paper_markdown_hf_namespace,
            "updated_at": _iso(datetime.now(timezone.utc)),
            "jobs": [],
            "summary": {},
            "error": "Hugging Face monitoring token is not configured",
        }

    api = HfApi(token=settings.hf_token)
    filesystem = HfFileSystem(token=settings.hf_token)
    remote_jobs = list(
        api.list_jobs(
            status=_JOB_STAGES,
            labels={"app": "pwc-paper-markdown"},
            timeout=10,
            namespace=settings.paper_markdown_hf_namespace,
            token=settings.hf_token,
        )
    )
    remote_jobs.sort(
        key=lambda job: (
            getattr(job, "created_at", None)
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    jobs: list[dict[str, Any]] = []
    for job in remote_jobs[:24]:
        labels = getattr(job, "labels", None) or {}
        run_id = labels.get("run_id")
        shard_id = labels.get("shard_id")
        status = getattr(job, "status", None)
        durations = getattr(job, "durations", None)
        jobs.append(
            {
                "id": str(getattr(job, "id", "")),
                "url": str(getattr(job, "url", "")),
                "stage": _stage(job),
                "stage_message": str(getattr(status, "message", "") or "")[:1000]
                or None,
                "mode": labels.get("mode"),
                "run_id": run_id,
                "shard_id": shard_id,
                "hardware": _hardware(job),
                "created_at": _iso(getattr(job, "created_at", None)),
                "started_at": _iso(getattr(job, "started_at", None)),
                "finished_at": _iso(getattr(job, "finished_at", None)),
                "duration_seconds": getattr(durations, "total_secs", None),
                "progress": _read_progress(filesystem, settings, run_id, shard_id),
            }
        )

    stages: dict[str, int] = {}
    for job in jobs:
        stages[job["stage"]] = stages.get(job["stage"], 0) + 1
    progress_rows = [job["progress"] for job in jobs if job["progress"]]
    latest_run_id = next((job.get("run_id") for job in jobs if job.get("run_id")), None)
    latest_run_jobs = [job for job in jobs if job.get("run_id") == latest_run_id]
    active_checkpoint_ages = []
    snapshot_now = datetime.now(timezone.utc)
    for job in latest_run_jobs:
        if job["stage"] not in {"SCHEDULING", "RUNNING"} or not job.get("progress"):
            continue
        updated_at = job["progress"].get("updated_at")
        try:
            parsed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        active_checkpoint_ages.append(
            max(
                0,
                int(
                    (snapshot_now - parsed.astimezone(timezone.utc)).total_seconds()
                    / 60
                ),
            )
        )
    summary = {
        "visible_jobs": len(jobs),
        "active_jobs": sum(
            count
            for stage, count in stages.items()
            if stage in {"SCHEDULING", "RUNNING"}
        ),
        "completed_jobs": stages.get("COMPLETED", 0),
        "failed_jobs": stages.get("ERROR", 0) + stages.get("CANCELED", 0),
        "processed_papers": sum(row["processed_papers"] for row in progress_rows),
        "succeeded_papers": sum(row["succeeded_papers"] for row in progress_rows),
        "failed_papers": sum(row["failed_papers"] for row in progress_rows),
        "extracted_images": sum(row["extracted_images"] for row in progress_rows),
        "latest_run_failed_jobs": sum(
            1 for job in latest_run_jobs if job["stage"] in {"ERROR", "CANCELED"}
        ),
        "oldest_active_checkpoint_age_minutes": (
            max(active_checkpoint_ages) if active_checkpoint_ages else 0
        ),
    }
    return {
        "available": True,
        "namespace": settings.paper_markdown_hf_namespace,
        "updated_at": _iso(datetime.now(timezone.utc)),
        "jobs": jobs,
        "summary": summary,
        "budgets": {
            "live": paper_markdown_budget_snapshot(
                remote_jobs,
                mode="live",
                ceiling_usd=settings.paper_markdown_incremental_monthly_budget_usd,
                planned_jobs=1,
                now=snapshot_now,
            ),
            "backfill": paper_markdown_budget_snapshot(
                remote_jobs,
                mode="backfill",
                ceiling_usd=settings.paper_markdown_backfill_budget_usd,
                planned_jobs=1,
                now=snapshot_now,
            ),
        },
        "error": None,
    }


def get_paper_markdown_job_monitor() -> dict[str, Any]:
    """Return a short-lived cached snapshot for the admin dashboard."""
    global _CACHE

    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE and now - _CACHE[0] < _CACHE_SECONDS:
            return dict(_CACHE[1])
        settings = get_settings()
        try:
            result = _fetch(settings)
        except (HfHubHTTPError, OSError, ValueError) as error:
            result = {
                "available": False,
                "namespace": settings.paper_markdown_hf_namespace,
                "updated_at": _iso(datetime.now(timezone.utc)),
                "jobs": [],
                "summary": {},
                "error": str(error)[:1000],
            }
        _CACHE = (now, result)
        return dict(result)


def get_cached_paper_markdown_job_monitor() -> dict[str, Any]:
    """Return cached monitor evidence without adding remote I/O to health scans."""

    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE and now - _CACHE[0] < _CACHE_SECONDS:
            return dict(_CACHE[1])
    return {"available": False, "jobs": [], "summary": {}, "error": None}


def clear_paper_markdown_job_monitor_cache() -> None:
    """Clear the process cache for tests and operator-triggered refreshes."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None
