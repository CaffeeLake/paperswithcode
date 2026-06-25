"""CRON job health evaluation for the admin dashboard."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import get_settings
from backend.services.cron_registry import CronJobDefinition, list_cron_jobs

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SCRIPTS_DIR = WORKFLOWS_DIR / "scripts"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_log_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value.replace("+00:00", "Z"), fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def to_iso8601(value: Optional[datetime | str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        dt = _parse_log_timestamp(value)
        if dt is None:
            return value
        value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_process_running(patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if "python" not in line or "grep" in line:
            continue
        if any(pattern in line for pattern in patterns):
            return True
    return False


def get_lock_state(
    lock_file: Optional[str], expected_runtime_minutes: int
) -> Dict[str, Any]:
    if not lock_file:
        return {"exists": False, "stale": False, "age_minutes": None}

    path = Path(lock_file)
    if not path.exists():
        return {"exists": False, "stale": False, "age_minutes": None}

    age_minutes = (_utcnow().timestamp() - path.stat().st_mtime) / 60
    stale = age_minutes > expected_runtime_minutes
    return {
        "exists": True,
        "stale": stale,
        "age_minutes": round(age_minutes, 1),
        "path": str(path),
    }


def fetch_db_freshness(query: str) -> Dict[str, Any]:
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=5,
        options="-c statement_timeout=10000",
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            row = cursor.fetchone() or {}
        metrics: Dict[str, Any] = {}
        last_write = row.get("last_write")
        if last_write is not None:
            metrics["last_write"] = last_write
            metrics["last_write_iso"] = to_iso8601(last_write)
        for key, value in row.items():
            if key == "last_write":
                continue
            metrics[key] = int(value or 0)
        return metrics
    finally:
        conn.close()


def fetch_thumbnail_cache_freshness() -> Dict[str, Any]:
    settings = get_settings()
    cache_dir = Path(settings.thumbnail_temp_cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parents[2] / cache_dir

    if not cache_dir.exists():
        return {"file_count": 0, "last_write": None, "last_write_iso": None}

    newest_mtime = None
    file_count = 0
    for path in cache_dir.rglob("*"):
        if not path.is_file():
            continue
        file_count += 1
        mtime = path.stat().st_mtime
        if newest_mtime is None or mtime > newest_mtime:
            newest_mtime = mtime

    last_write = (
        datetime.fromtimestamp(newest_mtime, tz=timezone.utc) if newest_mtime else None
    )
    return {
        "file_count": file_count,
        "last_write": last_write,
        "last_write_iso": to_iso8601(last_write),
        "recent_writes": file_count,
    }


def _minutes_since(value: Optional[datetime | str]) -> Optional[float]:
    dt = value if isinstance(value, datetime) else _parse_log_timestamp(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_utcnow() - dt.astimezone(timezone.utc)).total_seconds() / 60


def _db_is_stale(
    db_metrics: Dict[str, Any], stale_after_minutes: int
) -> tuple[bool, Optional[str]]:
    last_write = db_metrics.get("last_write")
    if last_write is None:
        return True, "no database writes recorded"

    age = _minutes_since(last_write)
    if age is None:
        return True, "could not parse database write timestamp"

    if age > stale_after_minutes:
        return (
            True,
            f"database writes are {age:.0f}m old (stale after {stale_after_minutes}m)",
        )

    recent_writes = db_metrics.get("recent_writes")
    if recent_writes is not None and recent_writes == 0:
        return True, "no recent database writes in the freshness window"

    return False, None


def evaluate_job_health(
    job: CronJobDefinition,
    log_status: Dict[str, Any],
    db_metrics: Optional[Dict[str, Any]] = None,
    lock_state: Optional[Dict[str, Any]] = None,
    dependency_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Combine log, process, lock, and DB signals into a dashboard status."""

    lock_state = lock_state or get_lock_state(
        job.lock_file, job.expected_runtime_minutes
    )
    running = bool(log_status.get("is_running")) or is_process_running(
        job.process_patterns
    )
    log_result = log_status.get("status", "unknown")
    work_metrics = dict(log_status.get("work_metrics") or {})
    db_metrics = db_metrics or {}
    log_no_work = log_result == "success_no_work"

    last_run_iso = to_iso8601(log_status.get("last_run"))
    last_db_write_iso = db_metrics.get("last_write_iso")
    recent_write_count = db_metrics.get("recent_writes")

    reasons: List[str] = []
    diagnostics: List[str] = []

    if lock_state.get("exists") and lock_state.get("stale") and not running:
        reasons.append(
            f"stale lock file ({lock_state.get('age_minutes')}m old, no active process)"
        )
        diagnostics.append(f"Inspect and remove stale lock: {lock_state.get('path')}")

    if running:
        start_age = _minutes_since(log_status.get("last_run"))
        if start_age is not None and start_age > job.expected_runtime_minutes:
            status = "stuck"
            reasons.append(
                f"process running for {start_age:.0f}m (expected <= {job.expected_runtime_minutes}m)"
            )
            diagnostics.append(
                "Check VPS process list and kill stuck wrapper/python if needed"
            )
        else:
            status = "running"
            reasons.append("process currently running")
    elif log_result == "failed":
        status = "broken"
        if log_status.get("error"):
            reasons.append(log_status["error"])
        else:
            reasons.append("latest log run failed")
        diagnostics.append(
            f"Tail `.github/workflows/scripts/logs/{job.log_name}_*.log`"
        )
    elif lock_state.get("exists") and lock_state.get("stale") and not running:
        status = "broken"
    elif log_no_work and job.healthy_no_work_allowed:
        status = "healthy"
        reasons.append("completed with no work (allowed for this job)")
    else:
        db_stale = False
        db_reason = None
        if job.db_freshness_query:
            if db_metrics.get("freshness_error"):
                db_stale = True
                db_reason = (
                    f"database freshness query failed: {db_metrics['freshness_error']}"
                )
            else:
                db_stale, db_reason = _db_is_stale(db_metrics, job.stale_after_minutes)
            if db_stale and db_reason:
                reasons.append(db_reason)
        elif job.id == "mirror_thumbnails_to_disk":
            db_stale, db_reason = _db_is_stale(db_metrics, job.stale_after_minutes)
            if db_stale and db_reason:
                reasons.append(db_reason or "thumbnail cache looks stale")

        log_success = log_result in {"success", "success_no_work"}

        if log_no_work and not job.healthy_no_work_allowed:
            reasons.append("log reports success but zero work items processed")
            if db_stale:
                status = "broken" if job.critical else "degraded"
                diagnostics.append("Reconcile log completion with database freshness")
            elif log_success:
                status = "degraded"
            else:
                status = "degraded"
        elif db_stale and job.db_freshness_query and job.critical:
            status = "broken"
            diagnostics.append(
                "Database freshness overrides log success — inspect SQL errors"
            )
        elif db_stale and job.db_freshness_query:
            status = "degraded"
        elif log_result == "unknown" and not db_metrics.get("last_write"):
            status = "unknown"
            reasons.append("insufficient log and database evidence")
        elif log_success or (db_metrics.get("last_write") and not db_stale):
            status = "healthy"
        elif log_result == "unknown":
            status = "unknown"
            reasons.append("no recent log completion found")
        else:
            status = "degraded"
            reasons.append(f"log status is {log_result}")

    if dependency_status and dependency_status not in {"healthy", "running"}:
        if status == "healthy":
            status = "degraded"
        reasons.append(f"dependency calculate_trending_scores is {dependency_status}")
        diagnostics.append(
            "Fix repo trending scores before trusting paper trending output"
        )

    if job.critical and status in {"broken", "stuck"} and not diagnostics:
        diagnostics.append("Critical writer — investigate immediately")

    if status in {"broken", "degraded", "stuck"} and not diagnostics:
        if job.db_freshness_query:
            diagnostics.append(
                "Compare latest log completion time with database write time"
            )
        else:
            diagnostics.append(
                f"Tail `.github/workflows/scripts/logs/{job.log_name}_*.log`"
            )

    status_reason = (
        "; ".join(dict.fromkeys(reasons)) if reasons else "operating normally"
    )

    return {
        "job_name": job.id,
        "display_name": job.display_name,
        "category": job.category,
        "status": status,
        "log_status": log_result,
        "status_reason": status_reason,
        "last_run": last_run_iso,
        "last_db_write": last_db_write_iso,
        "recent_write_count": recent_write_count,
        "duration": log_status.get("duration"),
        "is_running": running,
        "error": log_status.get("error"),
        "schedule": job.schedule,
        "critical": job.critical,
        "work_metrics": work_metrics,
        "work_summary": log_status.get("work_summary"),
        "db_metrics": {
            key: value
            for key, value in db_metrics.items()
            if key not in {"last_write", "last_write_iso"}
        },
        "lock_stale": bool(lock_state.get("stale")),
        "diagnostics": diagnostics[0] if diagnostics else None,
    }


def build_cron_dashboard() -> Dict[str, Any]:
    import sys

    if str(WORKFLOWS_DIR) not in sys.path:
        sys.path.insert(0, str(WORKFLOWS_DIR))
    from scripts.utils.cron_helpers import get_cron_job_status

    today = _utcnow().strftime("%Y%m%d")
    jobs: List[Dict[str, Any]] = []
    status_by_id: Dict[str, str] = {}

    for job in list_cron_jobs():
        log_status = get_cron_job_status(job.log_name, today)
        if job.process_patterns:
            log_status["is_running"] = log_status.get(
                "is_running"
            ) or is_process_running(job.process_patterns)

        db_metrics: Dict[str, Any] = {}
        if job.db_freshness_query:
            try:
                db_metrics = fetch_db_freshness(job.db_freshness_query)
            except Exception as exc:
                db_metrics = {"freshness_error": str(exc)}
        elif job.id == "mirror_thumbnails_to_disk":
            db_metrics = fetch_thumbnail_cache_freshness()

        lock_state = get_lock_state(job.lock_file, job.expected_runtime_minutes)
        dependency_status = None
        if job.id == "calculate_paper_trending_scores":
            dependency_status = status_by_id.get("calculate_trending_scores")

        evaluated = evaluate_job_health(
            job,
            log_status,
            db_metrics=db_metrics,
            lock_state=lock_state,
            dependency_status=dependency_status,
        )
        status_by_id[job.id] = evaluated["status"]
        jobs.append(evaluated)

    counts = {
        "healthy": sum(1 for job in jobs if job["status"] == "healthy"),
        "degraded": sum(1 for job in jobs if job["status"] == "degraded"),
        "broken": sum(1 for job in jobs if job["status"] == "broken"),
        "running": sum(1 for job in jobs if job["status"] == "running"),
        "stuck": sum(1 for job in jobs if job["status"] == "stuck"),
        "unknown": sum(1 for job in jobs if job["status"] == "unknown"),
    }

    critical_issues = [
        f"{job['display_name']}: {job['status_reason']}"
        for job in jobs
        if job["critical"] and job["status"] in {"broken", "stuck", "degraded"}
    ]

    what_to_check_next = next(
        (job["diagnostics"] for job in jobs if job["diagnostics"]),
        "All monitored jobs look healthy",
    )

    total = len(jobs)
    healthy_score = (counts["healthy"] / total * 100) if total else 0.0

    return {
        "timestamp": to_iso8601(_utcnow()),
        "jobs": jobs,
        "summary": {
            "total_jobs": total,
            **counts,
            "health_score": healthy_score,
            "critical_issues": critical_issues,
            "what_to_check_next": what_to_check_next,
        },
    }
