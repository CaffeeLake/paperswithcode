#!/usr/bin/env python3
"""
Hourly Cleanup of Stuck Cron Processes

This job detects and kills cron processes that have been running for too long,
preventing memory leaks and zombie processes from accumulating.

Schedule: Every hour
Dependencies: psutil
"""

import sys
import psutil
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cron.utils.cron_helpers import CronJobBase


class CleanupStuckProcessesJob(CronJobBase):
    """Hourly job to cleanup stuck cron processes."""

    def __init__(self):
        super().__init__(job_name="cleanup_stuck_processes", log_level="INFO")

        # Maximum runtime thresholds (in hours)
        self.max_runtime = {
            "extract_urls": 2,  # URL extraction should complete in < 2 hours
            "update_github_stars": 1.5,  # Stars update should complete in < 1.5 hours
            "update_citations": 1.5,  # Citations update should complete in < 1.5 hours
            "calculate_trending_scores": 1,  # Trending calculation should complete in < 1 hour
            "import_hf_daily_papers": 2,  # Daily import should complete in < 2 hours
        }

    def run(self):
        """Main execution logic for cleanup."""
        self.logger.info("Starting cleanup of stuck cron processes")

        killed_count = 0
        memory_freed = 0

        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "create_time", "memory_info"]
        ):
            try:
                cmdline = proc.info["cmdline"]
                if not cmdline:
                    continue

                # Check if this is a Python cron process
                cmdline_str = " ".join(cmdline)
                if "python" not in cmdline_str.lower():
                    continue

                # Check if it's running a cron job
                job_name = None
                for cron_job in self.max_runtime.keys():
                    if cron_job in cmdline_str:
                        job_name = cron_job
                        break

                if not job_name:
                    continue

                # Calculate runtime
                create_time = datetime.fromtimestamp(proc.info["create_time"])
                runtime = datetime.now() - create_time
                max_allowed = timedelta(hours=self.max_runtime[job_name])

                if runtime > max_allowed:
                    # This process has been running too long
                    memory_mb = proc.info["memory_info"].rss / 1024 / 1024
                    self.logger.warning(
                        f"Found stuck process: PID {proc.info['pid']}, "
                        f"Job: {job_name}, Runtime: {runtime}, "
                        f"Memory: {memory_mb:.1f}MB"
                    )

                    # Kill the process
                    try:
                        p = psutil.Process(proc.info["pid"])
                        p.terminate()
                        p.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        p.kill()
                    except Exception as e:
                        self.logger.error(f"Failed to kill PID {proc.info['pid']}: {e}")
                        continue

                    killed_count += 1
                    memory_freed += memory_mb
                    self.logger.info(f"Killed process PID {proc.info['pid']}")

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Log summary
        self.logger.info("=" * 80)
        self.logger.info("Cleanup Summary:")
        self.logger.info(f"  Stuck processes killed: {killed_count}")
        self.logger.info(f"  Memory freed: {memory_freed:.1f}MB")

        if killed_count == 0:
            self.logger.info("  No stuck processes found - all healthy!")

        self.logger.info("=" * 80)


if __name__ == "__main__":
    job = CleanupStuckProcessesJob()
    success = job.execute()
    sys.exit(0 if success else 1)
