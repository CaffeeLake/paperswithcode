#!/usr/bin/env python3
"""Stable, allowlisted launcher for production scheduled jobs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import fcntl
from datetime import datetime, timezone
from pathlib import Path

CURRENT = Path("/srv/paperswithcode/environments/production/current")
VENV = Path("/srv/paperswithcode/.venv")
LOG_DIR = Path("/var/lib/paperswithcode/production/cron-logs")

COMMANDS: dict[str, tuple[str, ...]] = {
    "update_github_stars": ("-m", "scripts.hourly.update_github_stars"),
    "update_citations": ("-m", "scripts.hourly.update_citations"),
    "extract_urls": ("-m", "url_extraction_agent.runner"),
    "extract_urls_select": ("-m", "url_extraction_agent.database", "select"),
    "extract_urls_persist": ("-m", "url_extraction_agent.database", "persist"),
    "calculate_trending_scores": (
        "-m",
        "scripts.hourly.calculate_trending_scores",
    ),
    "calculate_paper_trending_scores": (
        "-m",
        "scripts.hourly.calculate_paper_trending_scores",
    ),
    "update_hf_artifacts": ("-m", "scripts.hourly.update_hf_artifacts"),
    "import_hf_daily_papers": (
        "-m",
        "scripts.daily.import_hf_daily_papers",
    ),
    "preload_thumbnails": ("-m", "scripts.daily.preload_thumbnails"),
    "mirror_thumbnails_to_disk": (
        "-m",
        "scripts.daily.mirror_thumbnails_to_disk",
    ),
    "link_methods_by_references": (
        "-m",
        "scripts.weekly.link_methods_by_references",
    ),
    "link_papers_by_task_keywords": (
        "-m",
        "scripts.weekly.link_papers_by_task_keywords",
    ),
    "refresh_paper_embeddings": (
        "-m",
        "scripts.hourly.refresh_paper_embeddings",
    ),
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: pwc-cron <registered-job> [permitted arguments]", file=sys.stderr)
        return 2
    job = sys.argv[1]
    extra = sys.argv[2:]
    if any("\n" in arg or "\x00" in arg for arg in extra):
        print("invalid argument", file=sys.stderr)
        return 2
    manifest = json.loads((CURRENT / "release.json").read_text())
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "job": job,
        "release_id": manifest["release_id"],
        "git_sha": manifest["git_sha"],
    }
    with (LOG_DIR / "launcher.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    command = COMMANDS[job]
    env = os.environ.copy()
    env["PWC_ENVIRONMENT"] = "production"
    env["PWC_RELEASE_ID"] = manifest["release_id"]
    env["PWC_CRON_LOG_DIR"] = str(LOG_DIR)
    env["PYTHONPATH"] = str(CURRENT / ".github" / "workflows")
    if job in {"preload_thumbnails", "mirror_thumbnails_to_disk"}:
        env["PWC_THUMBNAIL_MUTATIONS_ENABLED"] = "true"
    argv = [str(VENV / "bin" / "python"), *command, *extra]
    lock_dir = Path(
        os.environ.get(
            "PWC_CRON_LOCK_DIR", "/var/lib/paperswithcode/production/cron-locks"
        )
    )
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / f"{job}.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"{job} is already running")
            return 0
        return subprocess.run(
            ["timeout", "-k", "60s", "2h", *argv],
            cwd=CURRENT,
            env=env,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
