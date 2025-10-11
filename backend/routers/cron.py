"""
FastAPI router for CRON job monitoring endpoints.

This module provides API endpoints for monitoring and managing CRON jobs.
"""

import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cron.utils.cron_helpers import get_cron_job_status


router = APIRouter()


class CronJobStatus(BaseModel):
    """Status information for a single cron job."""

    job_name: str
    category: str
    status: str  # success, success_no_work, failed, running, unknown
    last_run: Optional[str] = None
    duration: Optional[float] = None
    is_running: bool = False
    error: Optional[str] = None
    next_run: Optional[str] = None
    schedule: Optional[str] = None
    work_metrics: Dict[str, Any] = {}
    work_summary: Optional[str] = None


class CronJobsResponse(BaseModel):
    """Response model for cron jobs list."""

    timestamp: str
    jobs: List[CronJobStatus]
    summary: Dict[str, Any]


def get_available_jobs() -> Dict[str, List[str]]:
    """Get all available cron jobs organized by category."""
    cron_dir = Path(__file__).parent.parent.parent / "cron"
    jobs = {}

    categories = ["hourly", "daily", "weekly", "monthly"]
    for category in categories:
        category_dir = cron_dir / category
        if category_dir.exists():
            jobs[category] = []
            for script in category_dir.glob("*.py"):
                if script.name != "__init__.py":
                    jobs[category].append(script.stem)

    return jobs


def get_active_cron_jobs() -> List[Dict[str, str]]:
    """Get currently scheduled cron jobs from crontab with their schedules."""
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            return []

        active_jobs = []
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Extract job name and schedule from cron line
                if "cron/" in line:
                    # Extract schedule (first 5 fields)
                    parts = line.split()
                    if len(parts) >= 6:
                        schedule = " ".join(parts[:5])

                        # Look for patterns like cron/daily/job_name.py or cron/run_job.sh
                        match = re.search(
                            r"cron/(?:daily/|hourly/|weekly/|monthly/)?([^/\s]+)(?:\.py|\.sh)",
                            line,
                        )
                        if match:
                            job_name = match.group(1)

                            # Map wrapper script names to actual job names
                            job_name_mappings = {
                                "run_github_stars": "update_github_stars",
                                "run_trending_scores": "calculate_trending_scores",
                                "run_citations_hourly": "update_citations",
                                "run_extract_urls_hourly": "extract_urls",
                            }

                            # Use mapped name if it exists
                            mapped_name = job_name_mappings.get(job_name, job_name)

                            active_jobs.append(
                                {
                                    "name": mapped_name,
                                    "schedule": schedule,
                                    "full_line": line,
                                }
                            )

        return active_jobs

    except Exception as e:
        print(f"Error getting crontab: {e}")
        return []


def calculate_next_run(schedule: str) -> Optional[str]:
    """
    Calculate the next run time based on cron schedule.
    This is a simplified calculation - production would use croniter library.
    """
    try:
        # Parse cron schedule
        parts = schedule.split()
        if len(parts) != 5:
            return None

        minute, hour, day, month, weekday = parts
        now = datetime.utcnow()

        # Simplified logic for common patterns
        if minute == "*" and hour == "*":
            # Runs every minute
            next_run = now + timedelta(minutes=1)
            return next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif hour == "*":
            # Hourly jobs
            try:
                min_val = int(minute)
                if now.minute >= min_val:
                    next_run = now.replace(
                        minute=min_val, second=0, microsecond=0
                    ) + timedelta(hours=1)
                else:
                    next_run = now.replace(minute=min_val, second=0, microsecond=0)
                return next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
        else:
            # Daily or other jobs
            try:
                hour_val = int(hour)
                min_val = int(minute) if minute != "*" else 0

                next_run = now.replace(
                    hour=hour_val, minute=min_val, second=0, microsecond=0
                )
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass

        return "See crontab"

    except Exception:
        return None


def get_job_description(job_name: str, category: str) -> Optional[str]:
    """Get job description from docstring."""
    try:
        cron_dir = Path(__file__).parent.parent.parent / "cron"
        script_path = cron_dir / category / f"{job_name}.py"

        if not script_path.exists():
            return None

        with open(script_path, "r") as f:
            lines = f.readlines()

        in_docstring = False
        description = ""

        for line in lines:
            if '"""' in line and not in_docstring:
                in_docstring = True
                after_quotes = line.split('"""', 1)[1]
                if after_quotes.strip():
                    description = after_quotes.strip()
                    break
            elif in_docstring and '"""' in line:
                break
            elif in_docstring and line.strip():
                description = line.strip()
                break

        return description if description else None

    except Exception:
        return None


@router.get(
    "/cron/status",
    response_model=CronJobsResponse,
    summary="Get CRON jobs status",
)
async def get_cron_status(
    days: int = Query(
        1, ge=1, le=7, description="Number of days to look back for status"
    ),
):
    """
    Get comprehensive status of all CRON jobs.

    Returns information about:
    - Job execution status
    - Last run time and duration
    - Errors if any
    - Next scheduled run time
    - Overall system health
    """
    today = datetime.utcnow().strftime("%Y%m%d")

    # Get available and active jobs
    available_jobs = get_available_jobs()
    active_jobs_data = get_active_cron_jobs()
    active_jobs = {job["name"]: job for job in active_jobs_data}

    jobs_status = []

    # Map script names to actual log file names
    log_name_mapping = {
        "update_github_stars_optimized": "github_stars_optimized",
        "update_github_stars": "github_stars_cron",
        "update_citations": "update_citations_hourly",
        "extract_urls": "extract_urls_hourly",
        "calculate_trending_scores": "trending_scores_cron",
    }

    # Process each category
    for category, job_names in available_jobs.items():
        for job_name in job_names:
            # Skip wrapper jobs to avoid duplicates
            if "wrapper" in job_name:
                continue

            # Get the log name
            log_name = log_name_mapping.get(job_name, job_name)

            # Get job status from logs
            status = get_cron_job_status(log_name, today)

            # Get schedule info if job is active
            schedule = None
            next_run = None
            if job_name in active_jobs:
                schedule = active_jobs[job_name]["schedule"]
                next_run = calculate_next_run(schedule)

            # Convert last_run to ISO 8601 format with Z suffix (UTC)
            last_run_iso = None
            if status["last_run"]:
                try:
                    # Parse the timestamp (format: "2025-10-11 12:06:18")
                    dt = datetime.strptime(status["last_run"], "%Y-%m-%d %H:%M:%S")
                    # Convert to ISO 8601 with Z suffix
                    last_run_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    last_run_iso = status["last_run"]

            job_status = CronJobStatus(
                job_name=job_name,
                category=category,
                status=status["status"],
                last_run=last_run_iso,
                duration=status["duration"],
                is_running=status["is_running"],
                error=status["error"],
                next_run=next_run,
                schedule=schedule,
                work_metrics=status.get("work_metrics", {}),
                work_summary=status.get("work_summary"),
            )

            jobs_status.append(job_status)

    # Calculate summary statistics
    total_jobs = len(jobs_status)
    success_count = sum(1 for j in jobs_status if j.status == "success")
    success_no_work_count = sum(1 for j in jobs_status if j.status == "success_no_work")
    failed_count = sum(1 for j in jobs_status if j.status == "failed")
    running_count = sum(1 for j in jobs_status if j.is_running)
    unknown_count = sum(1 for j in jobs_status if j.status == "unknown")

    # For health score, count both "success" and "success_no_work" as healthy
    healthy_count = success_count + success_no_work_count

    summary = {
        "total_jobs": total_jobs,
        "success": success_count,
        "success_no_work": success_no_work_count,
        "failed": failed_count,
        "running": running_count,
        "unknown": unknown_count,
        "health_score": (healthy_count / total_jobs * 100) if total_jobs > 0 else 0,
    }

    return CronJobsResponse(
        timestamp=datetime.utcnow().isoformat() + "Z", jobs=jobs_status, summary=summary
    )


@router.get(
    "/cron/job/{job_name}",
    response_model=Dict[str, Any],
    summary="Get detailed status for a specific job",
)
async def get_job_detail(
    job_name: str,
    days: int = Query(3, ge=1, le=30, description="Number of days of history to fetch"),
):
    """
    Get detailed status and history for a specific CRON job.

    Returns:
    - Current status
    - Historical runs for the specified number of days
    - Performance metrics
    - Error history
    """
    job_history = []

    # Get status for the last N days
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y%m%d")
        status = get_cron_job_status(job_name, date)

        if status["exists"]:
            # Convert last_run to ISO 8601 format with Z suffix (UTC)
            last_run_iso = None
            if status["last_run"]:
                try:
                    dt = datetime.strptime(status["last_run"], "%Y-%m-%d %H:%M:%S")
                    last_run_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    last_run_iso = status["last_run"]

            job_history.append(
                {
                    "date": date,
                    "status": status["status"],
                    "last_run": last_run_iso,
                    "duration": status["duration"],
                    "error": status["error"],
                }
            )

    if not job_history:
        raise HTTPException(
            status_code=404, detail="Job not found or no logs available"
        )

    # Calculate performance metrics
    successful_runs = [h for h in job_history if h["status"] == "success"]
    failed_runs = [h for h in job_history if h["status"] == "failed"]

    durations = [h["duration"] for h in successful_runs if h["duration"] is not None]
    avg_duration = sum(durations) / len(durations) if durations else None

    return {
        "job_name": job_name,
        "current_status": job_history[0] if job_history else None,
        "history": job_history,
        "metrics": {
            "total_runs": len(job_history),
            "successful_runs": len(successful_runs),
            "failed_runs": len(failed_runs),
            "success_rate": (len(successful_runs) / len(job_history) * 100)
            if job_history
            else 0,
            "avg_duration": avg_duration,
        },
    }


@router.get(
    "/cron/health",
    summary="Get CRON system health",
)
async def get_cron_health():
    """
    Get overall CRON system health status.

    Returns a simple health check with critical job statuses.
    """
    today = datetime.utcnow().strftime("%Y%m%d")

    # Define critical jobs that must be running
    critical_jobs = [
        "github_stars_optimized",
        "update_citations_hourly",
        "extract_urls_hourly",
    ]

    all_healthy = True
    issues = []

    for job in critical_jobs:
        status = get_cron_job_status(job, today)
        if status["status"] == "failed":
            all_healthy = False
            issues.append(f"{job}: FAILED - {status.get('error', 'Unknown error')}")
        elif status["status"] == "unknown" and not status["is_running"]:
            all_healthy = False
            issues.append(f"{job}: NOT RUN TODAY")

    return {
        "healthy": all_healthy,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "issues": issues if not all_healthy else [],
        "message": "All critical jobs healthy"
        if all_healthy
        else f"{len(issues)} issue(s) detected",
    }
