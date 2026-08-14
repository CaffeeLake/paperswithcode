"""CRON job health evaluation for the admin dashboard."""

from __future__ import annotations

import json
import os
import fcntl
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import get_settings
from backend.services.cron_registry import CronJobDefinition, list_cron_jobs

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SCRIPTS_DIR = WORKFLOWS_DIR / "scripts"
GITHUB_REPOSITORY = "huggingface/paperswithcode"
WORKFLOW_STATUS_CACHE_SECONDS = 60
_WORKFLOW_STATUS_CACHE: Dict[tuple[str, str], tuple[float, Dict[str, Any]]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_log_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%a %Y-%m-%d %H:%M:%S %Z",
    ):
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
    result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,args="],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return False
    processes: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) != 3:
            continue
        pid, parent_pid, command = fields
        processes.append((int(pid), int(parent_pid), command))
    parents = {pid: parent_pid for pid, parent_pid, _command in processes}
    diagnostic_ancestry = {os.getpid()}
    cursor = os.getpid()
    while (parent := parents.get(cursor)) is not None:
        if parent in diagnostic_ancestry:
            break
        diagnostic_ancestry.add(parent)
        if parent == 1:
            break
        cursor = parent
    for pid, _parent_pid, command in processes:
        if pid in diagnostic_ancestry or "python" not in command or "grep" in command:
            continue
        if any(pattern in command for pattern in patterns):
            return True
    return False


def get_lock_state(
    lock_file: Optional[str], expected_runtime_minutes: int
) -> Dict[str, Any]:
    if not lock_file:
        return {
            "exists": False,
            "held": False,
            "probe_status": "not_applicable",
            "stale": False,
            "age_minutes": None,
        }

    path = Path(lock_file)
    if not path.exists():
        return {
            "exists": False,
            "held": False,
            "probe_status": "unlocked",
            "stale": False,
            "age_minutes": None,
        }

    age_minutes = (_utcnow().timestamp() - path.stat().st_mtime) / 60
    held: Optional[bool]
    probe_status = "unknown"
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                held = True
                probe_status = "held"
            else:
                held = False
                probe_status = "unlocked"
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    except (PermissionError, OSError):
        held = None
    return {
        "exists": True,
        "held": held,
        "probe_status": probe_status,
        # Backward-compatible field: only a confirmed held lock can be stale.
        "stale": held is True and age_minutes > expected_runtime_minutes,
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


def fetch_chat_monitor_output() -> Dict[str, Any]:
    path = Path(get_settings().cron_log_dir) / "chat-operational-alert-health.json"
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return {"monitor_record_available": False}
    if len(raw) > 16 * 1024:
        return {"monitor_record_available": False}
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"monitor_record_available": False}
    if not isinstance(payload, dict):
        return {"monitor_record_available": False}
    return {
        "monitor_record_available": True,
        "monitor_status": str(payload.get("status") or "unknown")[:16],
        "monitor_completed_at": str(payload.get("completed_at") or "")[:64] or None,
        "undelivered_alert_events": max(0, int(payload.get("pending") or 0)),
        "new_alert_events": max(0, int(payload.get("new_events") or 0)),
        "delivered_alert_events": max(0, int(payload.get("delivered") or 0)),
    }


def _gh_json(args: list[str], timeout: int = 10) -> tuple[Any, Optional[str]]:
    env = os.environ.copy()
    github_token = get_settings().github_token
    if github_token:
        env["GH_TOKEN"] = github_token
    env["GH_REPO"] = GITHUB_REPOSITORY

    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return None, str(exc)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "gh command failed").strip()
        return None, message

    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"failed to parse gh JSON: {exc}"


def _sanitized_adapter_error(value: object, adapter: str) -> str:
    message = str(value).lower()
    if any(token in message for token in ("auth", "credential", "401", "403")):
        return f"{adapter} authentication was rejected"
    if "permission" in message:
        return f"{adapter} permission denied"
    if "timeout" in message or "timed out" in message:
        return f"{adapter} request timed out"
    return f"{adapter} status is unavailable"


def _sanitized_job_error(value: object, job_id: str) -> str:
    message = str(value)
    lowered = message.lower()
    variables = sorted(set(re.findall(r"PWC_[A-Z0-9_]+", message)))
    variable = f" ({', '.join(variables)})" if variables else ""
    if any(token in lowered for token in ("credential", "token", "401", "403", "auth")):
        return f"{job_id} credential or authentication failure{variable}"
    if "429" in lowered or "rate limit" in lowered:
        return f"{job_id} upstream provider rate limiting"
    if "endpoint" in lowered:
        return f"{job_id} endpoint configuration or request failure{variable}"
    return f"{job_id} latest run failed"


def fetch_workflow_status(
    workflow_file: str,
    expected_jobs: tuple[str, ...] = (),
) -> Dict[str, Any]:
    """Fetch the latest GitHub Actions run for a workflow.

    This is best-effort: authentication or network failures should not hide fresh
    database writes, but when available the signal catches broken orchestration
    around jobs such as URL extraction's select/discover/persist pipeline.
    """

    cache_key = (workflow_file, "combined")
    cached = _WORKFLOW_STATUS_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < WORKFLOW_STATUS_CACHE_SECONDS:
        return dict(cached[1])

    def recent_runs(event: str) -> tuple[list[Dict[str, Any]], Optional[str]]:
        event_key = (workflow_file, event)
        event_cached = _WORKFLOW_STATUS_CACHE.get(event_key)
        if event_cached and now - event_cached[0] < WORKFLOW_STATUS_CACHE_SECONDS:
            return list(event_cached[1].get("runs") or []), event_cached[1].get("error")
        payload, event_error = _gh_json(
            [
                "run",
                "list",
                "--workflow",
                workflow_file,
                "--limit",
                "10",
                "--event",
                event,
                "--json",
                "databaseId,status,conclusion,createdAt,updatedAt,event,headBranch",
            ],
            timeout=8,
        )
        cached_payload = {"runs": payload or [], "error": event_error}
        _WORKFLOW_STATUS_CACHE[event_key] = (now, cached_payload)
        return list(payload or []), event_error

    scheduled_payload, error = recent_runs("schedule")
    if error:
        status = {
            "available": False,
            "workflow_file": workflow_file,
            "error": _sanitized_adapter_error(error, "GitHub Actions"),
        }
        _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
        return status

    manual_payload, manual_error = recent_runs("workflow_dispatch")
    list_payload = [*scheduled_payload, *manual_payload]
    list_payload.sort(key=lambda run: run.get("createdAt") or "", reverse=True)

    if not list_payload:
        status = {
            "available": True,
            "workflow_file": workflow_file,
            "status": "unknown",
            "conclusion": None,
            "error": "no workflow runs found",
        }
        _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
        return status

    scheduled_runs = list(scheduled_payload)
    manual_runs = list(manual_payload)
    active_runs = [
        run for run in list_payload if run.get("status") not in {None, "", "completed"}
    ]
    latest = scheduled_runs[0] if scheduled_runs else list_payload[0]
    run_id = latest.get("databaseId")
    view_payload = latest
    if run_id and len(expected_jobs) > 1:
        fetched_view, view_error = _gh_json(
            [
                "run",
                "view",
                str(run_id),
                "--json",
                "status,conclusion,createdAt,updatedAt,event,headBranch,jobs",
            ],
            timeout=10,
        )
        if view_error:
            view_payload = {
                **latest,
                "view_error": _sanitized_adapter_error(
                    view_error, "GitHub Actions job"
                ),
            }
        elif isinstance(fetched_view, dict):
            view_payload = {**latest, **fetched_view}

    jobs = view_payload.get("jobs") or []
    expected = set(expected_jobs)
    relevant_jobs = [job for job in jobs if not expected or job.get("name") in expected]
    failed_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("conclusion") not in {None, "", "success", "skipped"}
    ]
    running_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("status") not in {None, "", "completed"}
    ]

    status = {
        "available": True,
        "workflow_file": workflow_file,
        "run_id": run_id,
        "status": view_payload.get("status"),
        "conclusion": view_payload.get("conclusion"),
        "created_at": view_payload.get("createdAt"),
        "updated_at": view_payload.get("updatedAt"),
        "event": view_payload.get("event"),
        "head_branch": view_payload.get("headBranch"),
        "failed_jobs": [name for name in failed_jobs if name],
        "running_jobs": [name for name in running_jobs if name],
        "job_conclusions": {
            job.get("name"): job.get("conclusion")
            for job in relevant_jobs
            if job.get("name")
        },
        "view_error": view_payload.get("view_error"),
        "manual_query_error": (
            _sanitized_adapter_error(manual_error, "GitHub Actions manual-run")
            if manual_error
            else None
        ),
        "scheduled_run": scheduled_runs[0] if scheduled_runs else None,
        "manual_run": manual_runs[0] if manual_runs else None,
        "active_run": active_runs[0] if active_runs else None,
    }
    _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
    return status


def fetch_systemd_status(job: CronJobDefinition) -> Dict[str, Any]:
    """Read bounded timer/service properties for a registry-owned unit pair."""

    if job.scheduler != "systemd" or not job.systemd_timer or not job.systemd_service:
        return {"available": False, "error": "systemd units are not registered"}

    properties = {
        job.systemd_timer: (
            "LoadState,ActiveState,SubState,UnitFileState,LastTriggerUSec,"
            "NextElapseUSecRealtime"
        ),
        job.systemd_service: (
            "LoadState,ActiveState,SubState,Result,ExecMainStatus,"
            "ExecMainStartTimestamp,ExecMainExitTimestamp"
        ),
    }
    values: Dict[str, Dict[str, str]] = {}
    for unit, requested in properties.items():
        try:
            result = subprocess.run(
                ["systemctl", "show", unit, f"--property={requested}"],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return {"available": False, "error": "systemd status is unavailable"}
        if result.returncode != 0:
            return {
                "available": False,
                "error": "systemd status permission denied or unavailable",
            }
        values[unit] = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )

    timer = values[job.systemd_timer]
    service = values[job.systemd_service]
    return {
        "available": True,
        "timer": job.systemd_timer,
        "service": job.systemd_service,
        "enabled": timer.get("UnitFileState") in {"enabled", "enabled-runtime"},
        "timer_active": timer.get("ActiveState") == "active",
        "timer_state": timer.get("ActiveState"),
        "timer_substate": timer.get("SubState"),
        "last_trigger_at": timer.get("LastTriggerUSec") or None,
        "next_trigger_at": timer.get("NextElapseUSecRealtime") or None,
        "service_result": service.get("Result") or None,
        "exec_main_status": int(service.get("ExecMainStatus") or 0),
        "last_started_at": service.get("ExecMainStartTimestamp") or None,
        "last_completed_at": service.get("ExecMainExitTimestamp") or None,
        "service_active": service.get("ActiveState") == "active",
    }


def discover_scheduled_duties() -> set[str]:
    """Discover pwc-cron duties from release-owned workflow and unit source."""

    duties: set[str] = set()
    for workflow in WORKFLOWS_DIR.glob("cron-*.yml"):
        source = workflow.read_text(encoding="utf-8")
        if not re.search(r"^\s{2}schedule:\s*$", source, re.MULTILINE):
            continue
        duties.update(re.findall(r"pwc-cron\s+([a-z0-9_]+)", source))
    duties.discard("status")

    systemd_dir = WORKFLOWS_DIR.parents[1] / "deploy" / "systemd"
    for service in systemd_dir.glob("pwc-*.service"):
        match = re.search(
            r"^ExecStart=.*/pwc-cron\s+([a-z0-9_]+)",
            service.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            duties.add(match.group(1))
    return duties


def _schedule_slots(
    job: CronJobDefinition, now: datetime
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not job.schedule_policies:
        return None, None
    pairs = [policy.slots(now) for policy in job.schedule_policies]
    return max(pair[0] for pair in pairs), min(pair[1] for pair in pairs)


def _execution_health(
    job: CronJobDefinition,
    *,
    running: bool,
    log_status: Dict[str, Any],
    workflow_status: Dict[str, Any],
    systemd_status: Optional[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    previous_expected, next_expected = _schedule_slots(job, now)
    base = {
        "scheduler": job.scheduler,
        "last_expected_at": to_iso8601(previous_expected),
        "next_expected_at": to_iso8601(next_expected),
        "last_started_at": None,
        "last_completed_at": None,
    }

    if job.scheduler == "manual":
        result = log_status.get("status", "unknown")
        status = (
            "running"
            if running
            else (
                "broken"
                if result == "failed"
                else (
                    "healthy" if result in {"success", "success_no_work"} else "unknown"
                )
            )
        )
        return {
            **base,
            "status": status,
            "reason": (
                "manual invocation is active"
                if running
                else "latest manual invocation status"
            ),
        }

    grace = timedelta(minutes=job.schedule_grace_minutes)
    if job.scheduler == "systemd":
        evidence = systemd_status or {}
        if not evidence.get("available"):
            return {
                **base,
                "status": "unknown",
                "reason": "systemd timer evidence is unavailable",
            }
        base.update(
            last_started_at=to_iso8601(evidence.get("last_started_at")),
            last_completed_at=to_iso8601(evidence.get("last_completed_at")),
            next_expected_at=to_iso8601(evidence.get("next_trigger_at"))
            or base["next_expected_at"],
        )
        if not evidence.get("enabled") or not evidence.get("timer_active"):
            return {
                **base,
                "status": "broken",
                "reason": "systemd timer is disabled or inactive",
            }
        if evidence.get("service_active") or running:
            age = _minutes_since(evidence.get("last_started_at"))
            if age is not None and age > job.expected_runtime_minutes:
                return {
                    **base,
                    "status": "stuck",
                    "reason": f"systemd service exceeded its {job.expected_runtime_minutes}m runtime budget",
                }
            return {**base, "status": "running", "reason": "systemd service is active"}
        if evidence.get("service_result") not in {None, "", "success"} or evidence.get(
            "exec_main_status"
        ) not in {None, 0}:
            return {
                **base,
                "status": "broken",
                "reason": "latest systemd service invocation failed",
            }
        completed = _parse_log_timestamp(evidence.get("last_completed_at"))
        if previous_expected and (
            completed is None or completed < previous_expected - grace
        ):
            late = now > previous_expected + grace
            return {
                **base,
                "status": "broken" if late else "degraded",
                "reason": (
                    "expected systemd invocation is overdue"
                    if late
                    else "waiting for expected systemd invocation"
                ),
            }
        return {
            **base,
            "status": "healthy",
            "reason": "systemd timer and latest service exit are healthy",
        }

    evidence = workflow_status or {}
    if not evidence.get("available"):
        return {
            **base,
            "status": "unknown",
            "reason": "GitHub Actions evidence is unavailable",
        }
    scheduled = evidence.get("scheduled_run")
    # Backward compatibility for callers/tests that provide one normalized run.
    if (
        scheduled is None
        and evidence.get("event") in {None, "schedule"}
        and evidence.get("status")
    ):
        scheduled = {
            "status": evidence.get("status"),
            "conclusion": evidence.get("conclusion"),
            "createdAt": evidence.get("created_at"),
            "updatedAt": evidence.get("updated_at"),
        }
    active = evidence.get("active_run")
    if active and active.get("event") == "schedule":
        started = _parse_log_timestamp(active.get("createdAt"))
        base["last_started_at"] = to_iso8601(started)
        if started and now - started > timedelta(minutes=job.expected_runtime_minutes):
            return {
                **base,
                "status": "stuck",
                "reason": f"scheduled workflow exceeded its {job.expected_runtime_minutes}m runtime budget",
            }
        return {**base, "status": "running", "reason": "scheduled workflow is active"}
    if scheduled:
        started = _parse_log_timestamp(scheduled.get("createdAt"))
        completed = _parse_log_timestamp(scheduled.get("updatedAt"))
        base.update(
            last_started_at=to_iso8601(started), last_completed_at=to_iso8601(completed)
        )
        if scheduled.get("status") == "completed" and scheduled.get(
            "conclusion"
        ) not in {None, "", "success", "skipped"}:
            return {
                **base,
                "status": "broken",
                "reason": "latest scheduled workflow failed",
            }
        if scheduled.get("status") != "completed":
            return {
                **base,
                "status": "running",
                "reason": "scheduled workflow is active",
            }
        if previous_expected and (started is None or started < previous_expected):
            late = now > previous_expected + grace
            return {
                **base,
                "status": "broken" if late else "degraded",
                "reason": (
                    "scheduled workflow is overdue"
                    if late
                    else "waiting for the scheduled workflow to start"
                ),
            }
        return {
            **base,
            "status": "healthy",
            "reason": "latest scheduled workflow completed successfully",
        }

    if previous_expected:
        late = now > previous_expected + grace
        return {
            **base,
            "status": "broken" if late else "degraded",
            "reason": "no scheduled workflow run was found",
        }
    return {
        **base,
        "status": "unknown",
        "reason": "scheduled workflow evidence is missing",
    }


def _aggregate_health(execution: str, output: str) -> str:
    if "stuck" in {execution, output}:
        return "stuck"
    if "broken" in {execution, output}:
        return "broken"
    if "degraded" in {execution, output}:
        return "degraded"
    if "unknown" in {execution, output}:
        return "unknown"
    if "running" in {execution, output}:
        return "running"
    return "healthy"


_OUTPUT_RANK = {
    "healthy": 0,
    "running": 0,
    "unknown": 1,
    "degraded": 2,
    "broken": 3,
    "stuck": 4,
}


def _worse_output(current: str, candidate: str) -> str:
    return candidate if _OUTPUT_RANK[candidate] > _OUTPUT_RANK[current] else current


def _workflow_output_contract(
    status: str,
    reasons: List[str],
    _work: Dict[str, Any],
    _db: Dict[str, Any],
    workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    if status != "unknown":
        return status, reasons
    conclusion = workflow.get("conclusion")
    completed = workflow.get("status") == "completed"
    if completed and conclusion in {"success", "skipped"}:
        return "healthy", ["workflow completed its job-owned output contract"]
    return status, reasons


def _paper_markdown_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    _db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    remaining = int(work.get("missing_after_upstream", 0) or 0)
    if work.get("budget_exhausted") and remaining:
        status = _worse_output(status, "degraded")
        reasons.append(f"OCR budget is exhausted with {remaining} papers still missing")
    if work.get("remote_monitor_available") is False and status == "healthy":
        status = "unknown"
        reasons.append("remote OCR shard evidence is unavailable")
    terminal = int(work.get("terminal_shard_failures", 0) or 0)
    if terminal:
        status = _worse_output(status, "broken")
        reasons.append(f"{terminal} remote OCR shard(s) ended in failure")
    checkpoint_age = work.get("oldest_active_checkpoint_age_minutes")
    if checkpoint_age is not None and float(checkpoint_age) > 30:
        status = _worse_output(status, "broken")
        reasons.append("remote OCR progress checkpoint is stale")
    return status, reasons


def _paper_embeddings_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    missing = int(db.get("missing_embeddings", 0) or 0)
    candidates = work.get("candidates")
    embedded = int(work.get("embeddings_updated", work.get("embedded", 0)) or 0)
    if missing and candidates == 0:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{missing} eligible embeddings are missing despite a no-work run"
        )
    elif missing and candidates is not None and embedded == 0:
        status = _worse_output(status, "degraded")
        reasons.append(f"no embeddings were written while {missing} remain eligible")
    return status, reasons


def _hf_import_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    _db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    if work.get("upstream_fetch_succeeded") is False:
        return "broken", reasons + ["Hugging Face daily-paper feed fetch failed"]
    if work.get("upstream_fetch_succeeded") is True:
        failed = int(work.get("failed", 0) or 0)
        if failed:
            status = _worse_output(status, "degraded")
            reasons.append(f"{failed} imported paper(s) failed")
        elif status == "unknown":
            status = "healthy"
            reasons.append("upstream feed was fetched and the import summary completed")
    return status, reasons


def _github_stars_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    _db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    for queue in ("fresh", "weekly"):
        stops = int(work.get(f"{queue}_rate_limit_stops", 0) or 0)
        selected = int(work.get(f"{queue}_selected_groups", 0) or 0)
        successes = int(work.get(f"{queue}_successes", 0) or 0)
        if stops:
            candidate = "broken" if selected and not successes else "degraded"
            status = _worse_output(status, candidate)
            reasons.append(f"{queue} queue exhausted its GitHub rate-limit reserve")
    return status, reasons


def _counter_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    scanned = work.get(
        "papers_scanned",
        work.get(
            "papers_processed",
            work.get("repositories_processed", work.get("eligible_population")),
        ),
    )
    if scanned is None and db.get("papers_scanned") is None and status == "healthy":
        status = "unknown"
        reasons.append("job-owned scanned/fetched counters are unavailable")
    return status, reasons


def _provider_counter_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    status, reasons = _counter_contract(status, reasons, work, db, workflow)
    throttled = int(work.get("rate_limit_hits", 0) or 0)
    failures = int(
        work.get("api_errors", 0)
        or work.get("papers_failed", 0)
        or work.get("artifacts_failed", 0)
        or 0
    )
    if throttled:
        status = _worse_output(status, "degraded")
        reasons.append(f"upstream provider rate-limited {throttled} request(s)")
    if failures:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failures} upstream item(s) failed")
    return status, reasons


def _trending_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    status, reasons = _counter_contract(status, reasons, work, db, workflow)
    eligible = int(db.get("eligible_population", 0) or 0)
    positive = int(
        db.get("fresh_positive_scores", db.get("fresh_github_component_scores", 0)) or 0
    )
    if eligible and not positive:
        status = _worse_output(status, "broken")
        reasons.append("eligible population produced no positive trending components")
    elif "eligible_population" in db and eligible == 0:
        status = "healthy"
        reasons.append("eligible population is empty; successful no-work is valid")
    return status, reasons


def _organization_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    status, reasons = _counter_contract(status, reasons, work, db, workflow)
    missing = int(db.get("missing_today_snapshots", 0) or 0)
    if missing:
        status = _worse_output(status, "degraded")
        reasons.append(f"{missing} managed organization(s) missed today's snapshot")
    return status, reasons


def _thumbnail_preload_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    status, reasons = _workflow_output_contract(status, reasons, work, db, workflow)
    failures = int(work.get("failed_downloads", 0) or 0)
    if failures:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failures} thumbnail download(s) failed")
    return status, reasons


def _backfill_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    stale_running = int(db.get("stale_running", 0) or 0)
    if stale_running:
        status = _worse_output(status, "broken")
        reasons.append(f"{stale_running} stale database run row(s) block progress")
        blocking_age = int(db.get("blocking_run_age_minutes", 0) or 0)
        cursor = db.get("resume_cursor")
        if blocking_age:
            reasons.append(f"blocking run age is {blocking_age}m")
        if cursor is not None:
            reasons.append(f"resume cursor is {cursor}")
    failed_runs = int(db.get("failed_runs", 0) or 0)
    if failed_runs:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failed_runs} backfill run partition(s) are failed")
    provider_429 = int(db.get("provider_429_rows", 0) or 0)
    retryable = int(db.get("retryable_failures", 0) or 0)
    if provider_429:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"provider rate limiting affects {provider_429} partition(s); "
            f"{retryable} retryable item(s) remain"
        )
    throttled = int(
        work.get("provider_rate_limit_hits", work.get("rate_limit_hits", 0)) or 0
    )
    if throttled:
        status = _worse_output(status, "degraded")
        reasons.append(f"provider throttled {throttled} request(s)")
    return status, reasons


def _curation_thumbnail_contract(
    status: str,
    reasons: List[str],
    _work: Dict[str, Any],
    db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    stale = int(db.get("stale_processing", 0) or 0)
    failed = int(db.get("failed", 0) or 0)
    if stale:
        status = _worse_output(status, "broken")
        reasons.append(f"{stale} curation thumbnail request(s) are stuck processing")
    if failed:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failed} curation thumbnail request(s) failed")
    return status, reasons


def _chat_alert_contract(
    status: str,
    reasons: List[str],
    work: Dict[str, Any],
    _db: Dict[str, Any],
    _workflow: Dict[str, Any],
) -> tuple[str, List[str]]:
    if not work.get("monitor_record_available"):
        return "unknown", reasons + [
            "content-free monitor output record is unavailable"
        ]
    age = _minutes_since(work.get("monitor_completed_at"))
    if age is None or age > 5:
        return "broken", reasons + ["latest operational poll output is stale"]
    pending = int(work.get("undelivered_alert_events", 0) or 0)
    monitor_status = work.get("monitor_status")
    if pending or monitor_status == "degraded":
        return "broken", reasons + [
            f"{pending} operational alert event(s) remain undelivered"
        ]
    if monitor_status == "dormant":
        return "healthy", ["monitor is dormant because production chat is disabled"]
    if monitor_status == "healthy":
        return "healthy", [
            "latest content-free operational poll completed successfully"
        ]
    return "unknown", reasons + ["operational monitor output state is unknown"]


OUTPUT_EVALUATORS = {
    "generic": lambda status, reasons, _work, _db, _workflow: (status, reasons),
    "github_stars": _github_stars_contract,
    "hot_github_trending": lambda status, reasons, _work, _db, _workflow: (
        status,
        reasons,
    ),
    "repository_trending": _trending_contract,
    "paper_trending": _trending_contract,
    "hf_paper_import": _hf_import_contract,
    "citations": _provider_counter_contract,
    "hf_artifacts": _provider_counter_contract,
    "paper_markdown": _paper_markdown_contract,
    "paper_embeddings": _paper_embeddings_contract,
    "organization_sync": _organization_contract,
    "organization_trending": _organization_contract,
    "backfill": _backfill_contract,
    "thumbnail_preload": _thumbnail_preload_contract,
    "thumbnail_mirror": _workflow_output_contract,
    "weekly_linker": _workflow_output_contract,
    "curation_thumbnails": _curation_thumbnail_contract,
    "chat_alert_monitor": _chat_alert_contract,
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


def _recent_log_success(
    job: CronJobDefinition, log_status: Dict[str, Any]
) -> tuple[bool, Optional[str]]:
    if log_status.get("status") not in {"success", "success_no_work"}:
        return False, None
    age = _minutes_since(log_status.get("last_run"))
    if age is None:
        return False, None
    if age > job.stale_after_minutes:
        return False, None
    return True, f"latest successful log run is {age:.0f}m old"


def evaluate_job_health(
    job: CronJobDefinition,
    log_status: Dict[str, Any],
    db_metrics: Optional[Dict[str, Any]] = None,
    lock_state: Optional[Dict[str, Any]] = None,
    dependency_status: Optional[str] = None,
    workflow_status: Optional[Dict[str, Any]] = None,
    systemd_status: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Combine log, process, lock, and DB signals into a dashboard status."""

    lock_state = lock_state or get_lock_state(
        job.lock_file, job.expected_runtime_minutes
    )
    now = now or _utcnow()
    running = bool(log_status.get("is_running")) or is_process_running(
        job.process_patterns
    )
    log_result = log_status.get("status", "unknown")
    work_metrics = dict(log_status.get("work_metrics") or {})
    db_metrics = db_metrics or {}
    log_no_work = log_result == "success_no_work"
    safe_log_error = (
        _sanitized_job_error(log_status["error"], job.id)
        if log_status.get("error")
        else None
    )

    last_run_iso = to_iso8601(log_status.get("last_run"))
    last_db_write_iso = db_metrics.get("last_write_iso")
    recent_write_count = db_metrics.get("recent_writes")

    reasons: List[str] = []
    diagnostics: List[str] = []

    db_stale = False
    db_reason: Optional[str] = None
    if job.db_freshness_query:
        if db_metrics.get("freshness_error"):
            db_stale = True
            db_reason = (
                f"database freshness query failed: {db_metrics['freshness_error']}"
            )
        else:
            db_stale, db_reason = _db_is_stale(db_metrics, job.stale_after_minutes)

    recent_log_success, recent_log_reason = _recent_log_success(job, log_status)
    if (
        job.id == "update_hot_github_trending"
        and db_metrics.get("hot_repository_count") == 0
        and recent_log_success
    ):
        db_stale = False
        db_reason = None

    # An inode may persist forever; only a currently held kernel lock is evidence.
    # Give the wrapper a short handoff window before calling a held orphan broken.
    lock_blocks_job = (
        lock_state.get("held") is True
        and not running
        and float(lock_state.get("age_minutes") or 0) > 1
    )

    if lock_blocks_job:
        reasons.append(
            f"lock is held with no matching process ({lock_state.get('age_minutes')}m inode age)"
        )
        diagnostics.append("Inspect the lock owner and wrapper process ancestry")
    elif lock_state.get("held") is True and not running:
        running = True
        reasons.append("lock is held during the wrapper-to-Python handoff window")

    if running:
        start_age = _minutes_since(log_status.get("last_run"))
        if start_age is not None and start_age > job.expected_runtime_minutes:
            status = "stuck"
            reasons.append(
                f"process running for {start_age:.0f}m (expected <= {job.expected_runtime_minutes}m)"
            )
            diagnostics.append("Inspect the process ancestry and bounded runtime logs")
        else:
            status = "running"
            reasons.append("process currently running")
    elif log_result == "failed":
        status = "broken"
        if safe_log_error:
            reasons.append(safe_log_error)
        else:
            reasons.append("latest log run failed")
        diagnostics.append(f"Tail `{get_settings().cron_log_dir}/{job.log_name}_*.log`")
    elif lock_blocks_job:
        status = "broken"
    elif log_no_work and job.healthy_no_work_allowed:
        status = "healthy"
        reasons.append("completed with no work (allowed for this job)")
    else:
        if job.id == "mirror_thumbnails_to_disk":
            db_stale, db_reason = _db_is_stale(db_metrics, job.stale_after_minutes)
            if db_stale and db_reason:
                reasons.append(db_reason or "thumbnail cache looks stale")

        import_recent_no_work = (
            job.id == "import_hf_daily_papers"
            and db_stale
            and recent_log_success
            and job.healthy_no_work_allowed
        )

        if (
            db_stale
            and db_reason
            and db_reason not in reasons
            and not import_recent_no_work
        ):
            reasons.append(db_reason)

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
        elif import_recent_no_work:
            status = "healthy"
            reasons.append(recent_log_reason or "recent import completed successfully")
            reasons.append("no new papers imported in the freshness window")
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

    if job.id == "update_hot_github_trending":
        oldest_wait = db_metrics.get("oldest_eligible_wait_minutes", 0)
        stale_scores = db_metrics.get("stale_paper_scores", 0)
        one_snapshot = db_metrics.get("one_snapshot_over_30m", 0)
        reserve_stops = work_metrics.get("rate_limit_stops", 0)
        remaining = work_metrics.get("rate_limit_remaining")
        reserve = work_metrics.get("rate_limit_reserve")
        credential_failures = work_metrics.get("credential_failures", 0)
        credential = work_metrics.get("credential", "GitHub credential")

        if oldest_wait > 30:
            status = "broken"
            reasons.append(f"oldest eligible hot repository has waited {oldest_wait}m")
        if stale_scores:
            status = "broken"
            reasons.append(f"{stale_scores} hot paper scores are missing or stale")
        if credential_failures:
            status = "broken"
            reasons.append(
                f"{credential} was rejected by GitHub "
                f"({credential_failures} failed requests)"
            )
        if one_snapshot and status == "healthy":
            status = "degraded"
            reasons.append(
                f"{one_snapshot} hot repositories have one snapshot after 30m"
            )
        if reserve_stops:
            if status == "healthy":
                status = "degraded"
            reasons.append(f"rate-limit reserve stopped {reserve_stops} run(s)")
        if (
            remaining is not None
            and reserve is not None
            and int(remaining) < int(reserve)
        ):
            status = "broken"
            reasons.append(
                f"rate-limit reserve violated ({remaining} remaining < {reserve})"
            )

    if job.id == "update_github_stars" and not running:
        for queue in ("fresh", "weekly"):
            selected = int(work_metrics.get(f"{queue}_selected_groups", 0) or 0)
            successes = int(work_metrics.get(f"{queue}_successes", 0) or 0)
            failures = int(work_metrics.get(f"{queue}_failures", 0) or 0)
            credential_failures = int(
                work_metrics.get(f"{queue}_credential_failures", 0) or 0
            )
            credential = work_metrics.get(
                f"{queue}_credential", f"{queue} GitHub credential"
            )
            if selected and successes == 0 and failures:
                status = "broken"
                if credential_failures:
                    reasons.append(
                        f"{credential} was rejected by GitHub; "
                        f"the {queue} queue had no successful fetches"
                    )
                else:
                    reasons.append(
                        f"{queue} GitHub queue had no successful fetches "
                        f"({failures} failures)"
                    )
            elif credential_failures:
                if status == "healthy":
                    status = "degraded"
                reasons.append(
                    f"{credential} had {credential_failures} rejected request(s)"
                )

    if dependency_status and dependency_status not in {"healthy", "running"}:
        if status == "healthy":
            status = "degraded"
        reasons.append(f"dependency calculate_trending_scores is {dependency_status}")
        diagnostics.append(
            "Fix repo trending scores before trusting paper trending output"
        )

    workflow_status = workflow_status or {}
    evaluator = OUTPUT_EVALUATORS[job.output_evaluator or "generic"]
    status, reasons = evaluator(
        status, reasons, work_metrics, db_metrics, workflow_status
    )
    if (
        job.id == "process_curation_thumbnails"
        and systemd_status
        and systemd_status.get("service_result") == "success"
        and not any(
            int(db_metrics.get(key, 0) or 0)
            for key in ("queued", "processing", "stale_processing", "failed")
        )
    ):
        status = "healthy"
        reasons = ["latest queue poll completed and no thumbnail work is pending"]
    output_status = status
    output_reason = (
        "; ".join(dict.fromkeys(reasons)) if reasons else "job-owned output is fresh"
    )
    execution_health = _execution_health(
        job,
        running=running,
        log_status=log_status,
        workflow_status=workflow_status,
        systemd_status=systemd_status,
        now=now,
    )
    status = _aggregate_health(execution_health["status"], output_status)
    if execution_health["status"] not in {"healthy", "running"}:
        diagnostics.append(execution_health["reason"])

    if job.critical and status in {"broken", "stuck"} and not diagnostics:
        diagnostics.append("Critical writer — investigate immediately")

    if status in {"broken", "degraded", "stuck"} and not diagnostics:
        if job.db_freshness_query:
            diagnostics.append(
                "Compare latest log completion time with database write time"
            )
        else:
            diagnostics.append(
                f"Tail `{get_settings().cron_log_dir}/{job.log_name}_*.log`"
            )

    status_reason = f"Execution: {execution_health['reason']}; Output: {output_reason}"

    return {
        "job_name": job.id,
        "display_name": job.display_name,
        "category": job.category,
        "dashboard_group": job.dashboard_group,
        "status": status,
        "log_status": log_result,
        "status_reason": status_reason,
        "last_run": last_run_iso,
        "last_db_write": last_db_write_iso,
        "recent_write_count": recent_write_count,
        "duration": log_status.get("duration"),
        "is_running": running,
        "error": safe_log_error,
        "schedule": job.schedule,
        "critical": job.critical,
        "work_metrics": work_metrics,
        "work_summary": log_status.get("work_summary"),
        "db_metrics": {
            key: value
            for key, value in db_metrics.items()
            if key not in {"last_write", "last_write_iso"}
        },
        "workflow_status": workflow_status or None,
        "systemd_status": systemd_status,
        "execution_health": execution_health,
        "output_health": {
            "status": output_status,
            "reason": output_reason,
            "last_verified_at": last_db_write_iso or last_run_iso,
        },
        "lock_stale": bool(lock_state.get("stale")),
        "lock_state": lock_state,
        "diagnostics": diagnostics[0] if diagnostics else None,
        "diagnostic_groups": {
            "scheduler_orchestration": (
                [execution_health["reason"]]
                if execution_health["status"] not in {"healthy", "running"}
                else []
            ),
            "output_freshness_completeness": list(dict.fromkeys(reasons)),
        },
    }


def build_cron_dashboard() -> Dict[str, Any]:
    import sys

    if str(WORKFLOWS_DIR) not in sys.path:
        sys.path.insert(0, str(WORKFLOWS_DIR))
    from scripts.utils.cron_helpers import get_cron_job_status

    today = _utcnow().strftime("%Y%m%d")
    jobs: List[Dict[str, Any]] = []
    status_by_id: Dict[str, str] = {}
    definitions = list(list_cron_jobs())
    workflow_definitions = [job for job in definitions if job.workflow_file]
    with ThreadPoolExecutor(max_workers=6) as executor:
        workflow_results = dict(
            zip(
                (job.id for job in workflow_definitions),
                executor.map(
                    lambda job: fetch_workflow_status(
                        job.workflow_file or "",
                        expected_jobs=job.workflow_jobs,
                    ),
                    workflow_definitions,
                ),
            )
        )

    def get_recent_log_status(job: CronJobDefinition) -> Dict[str, Any]:
        max_days = max(0, min(14, job.stale_after_minutes // (24 * 60) + 1))
        latest_status = get_cron_job_status(job.log_name, today)
        if latest_status.get("exists") or max_days == 0:
            return latest_status

        for days_back in range(1, max_days + 1):
            date = (_utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
            candidate = get_cron_job_status(job.log_name, date)
            if candidate.get("exists"):
                return candidate
        return latest_status

    for job in definitions:
        log_status = get_recent_log_status(job)
        if job.id == "paper_markdown_backfill":
            from backend.services.paper_markdown_job_monitor import (
                get_paper_markdown_job_monitor,
            )

            remote = get_paper_markdown_job_monitor()
            metrics = dict(log_status.get("work_metrics") or {})
            metrics["remote_monitor_available"] = bool(remote.get("available"))
            if remote.get("available"):
                summary = remote.get("summary") or {}
                metrics["terminal_shard_failures"] = int(
                    summary.get("latest_run_failed_jobs", 0) or 0
                )
                metrics["oldest_active_checkpoint_age_minutes"] = int(
                    summary.get("oldest_active_checkpoint_age_minutes", 0) or 0
                )
            log_status["work_metrics"] = metrics
        elif job.id == "monitor_chat_operational_alerts":
            metrics = dict(log_status.get("work_metrics") or {})
            metrics.update(fetch_chat_monitor_output())
            log_status["work_metrics"] = metrics
        if job.process_patterns:
            log_status["is_running"] = log_status.get(
                "is_running"
            ) or is_process_running(job.process_patterns)

        db_metrics: Dict[str, Any] = {}
        if job.db_freshness_query:
            try:
                db_metrics = fetch_db_freshness(job.db_freshness_query)
            except Exception as exc:
                db_metrics = {
                    "freshness_error": _sanitized_adapter_error(
                        exc, "database freshness"
                    )
                }
        elif job.id == "mirror_thumbnails_to_disk":
            db_metrics = fetch_thumbnail_cache_freshness()

        lock_state = get_lock_state(job.lock_file, job.expected_runtime_minutes)
        dependency_status = None
        if job.id == "calculate_paper_trending_scores":
            dependency_status = status_by_id.get("calculate_trending_scores")
        workflow_status = None
        if job.workflow_file:
            workflow_status = workflow_results[job.id]
        systemd_status = (
            fetch_systemd_status(job) if job.scheduler == "systemd" else None
        )

        evaluated = evaluate_job_health(
            job,
            log_status,
            db_metrics=db_metrics,
            lock_state=lock_state,
            dependency_status=dependency_status,
            workflow_status=workflow_status,
            systemd_status=systemd_status,
        )
        status_by_id[job.id] = evaluated["status"]
        jobs.append(evaluated)

    scheduled_jobs = [job for job in jobs if job["category"] != "manual"]
    manual_jobs = [job for job in jobs if job["category"] == "manual"]
    counts = {
        state: sum(1 for job in scheduled_jobs if job["status"] == state)
        for state in ("healthy", "degraded", "broken", "running", "stuck", "unknown")
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

    total = len(scheduled_jobs)
    passing = counts["healthy"] + counts["running"]
    healthy_score = (passing / total * 100) if total else 0.0
    registered_ids = {
        job.id
        for job in list_cron_jobs()
        if job.scheduler in {"github_actions", "systemd"}
    }
    discovered_ids = discover_scheduled_duties()
    registered_scheduled = len(registered_ids)
    discovered_scheduled = len(discovered_ids)
    monitored_duties = len(registered_ids & discovered_ids)
    gap_ids = sorted(discovered_ids - registered_ids)

    return {
        "timestamp": to_iso8601(_utcnow()),
        "jobs": jobs,
        "manual_operations": manual_jobs,
        "summary": {
            "total_jobs": total,
            **counts,
            "health_score": healthy_score,
            "critical_issues": critical_issues,
            "what_to_check_next": what_to_check_next,
            "coverage": {
                "registered_scheduled_duties": registered_scheduled,
                "discovered_scheduled_duties": discovered_scheduled,
                "monitored_duties": monitored_duties,
                "coverage_gaps": len(gap_ids),
                "gap_ids": gap_ids,
            },
        },
    }
