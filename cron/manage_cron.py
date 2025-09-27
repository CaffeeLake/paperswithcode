#!/usr/bin/env python3
"""
CRON Job Management Script

Utility script to manage and monitor cron jobs for the PapersWithCode project.

Usage:
    python cron/manage_cron.py status [job_name] [date]
    python cron/manage_cron.py list
    python cron/manage_cron.py test <job_name>
    python cron/manage_cron.py cleanup
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys

from cron.utils.cron_helpers import get_cron_job_status, cleanup_old_logs


def list_cron_jobs():
    """List all available cron jobs."""
    cron_dir = Path(__file__).parent

    print("Available CRON Jobs:")
    print("=" * 50)

    categories = ["hourly", "daily", "weekly", "monthly"]

    for category in categories:
        category_dir = cron_dir / category
        if category_dir.exists():
            print(f"\n{category.upper()} Jobs:")
            print("-" * 20)

            for script in category_dir.glob("*.py"):
                if script.name != "__init__.py":
                    job_name = script.stem
                    print(f"  - {job_name}")

                    # Try to get description from docstring
                    try:
                        with open(script, "r") as f:
                            lines = f.readlines()

                        # Look for description in docstring
                        in_docstring = False
                        description = ""

                        for line in lines:
                            if '"""' in line and not in_docstring:
                                in_docstring = True
                                # Check if description is on the same line
                                after_quotes = line.split('"""', 1)[1]
                                if after_quotes.strip():
                                    description = after_quotes.strip()
                                    break
                            elif in_docstring and '"""' in line:
                                break
                            elif in_docstring and line.strip():
                                description = line.strip()
                                break

                        if description:
                            print(f"    {description}")

                    except Exception:
                        pass


def show_job_status(job_name: str = None, date: str = None):
    """Show status of cron jobs."""
    if job_name:
        # Show status for specific job
        status = get_cron_job_status(job_name, date)
        print(f"Status for {job_name}:")
        print("=" * 50)
        print(f"Date: {status['date']}")
        print(f"Log file: {status['log_file']}")
        print(f"Exists: {status['exists']}")

        if status["exists"]:
            print(f"Status: {status['status']}")
            print(f"Last run: {status['last_run']}")
            if status["duration"]:
                print(f"Duration: {status['duration']:.2f} seconds")
            if status["error"]:
                print(f"Error: {status['error']}")
        else:
            print("No log file found for this job/date")

    else:
        # Show status for all jobs
        cron_dir = Path(__file__).parent
        today = datetime.now().strftime("%Y%m%d")

        print(f"CRON Job Status Summary - {today}")
        print("=" * 60)

        categories = ["daily", "weekly", "monthly"]

        for category in categories:
            category_dir = cron_dir / category
            if category_dir.exists():
                print(f"\n{category.upper()} Jobs:")
                print("-" * 30)

                for script in category_dir.glob("*.py"):
                    if script.name != "__init__.py":
                        job_name = script.stem
                        status = get_cron_job_status(job_name, today)

                        status_icon = (
                            "✓"
                            if status["status"] == "success"
                            else "✗"
                            if status["status"] == "failed"
                            else "?"
                        )
                        print(
                            f"  {status_icon} {job_name:<25} {status['status']:<10} {status['last_run'] or 'Never'}"
                        )


def test_job(job_name: str):
    """Test run a specific cron job."""
    cron_dir = Path(__file__).parent

    # Find the job script
    job_script = None
    categories = ["daily", "weekly", "monthly"]

    for category in categories:
        script_path = cron_dir / category / f"{job_name}.py"
        if script_path.exists():
            job_script = script_path
            break

    if not job_script:
        print(f"Error: Job '{job_name}' not found")
        return False

    print(f"Testing cron job: {job_name}")
    print(f"Script: {job_script}")
    print("=" * 50)

    # Run the job script
    import subprocess
    import sys

    try:
        # Change to project root directory
        project_root = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, str(job_script)],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        print("STDOUT:")
        print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        print(f"\nExit code: {result.returncode}")

        return result.returncode == 0

    except Exception as e:
        print(f"Error running job: {e}")
        return False


def cleanup_logs():
    """Clean up old log files."""
    print("Cleaning up old log files...")

    try:
        cleanup_old_logs(days_to_keep=30)
        print("Log cleanup completed successfully")
    except Exception as e:
        print(f"Error during log cleanup: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Manage CRON jobs for PapersWithCode")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    subparsers.add_parser("list", help="List all available cron jobs")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show cron job status")
    status_parser.add_argument("job_name", nargs="?", help="Specific job name to check")
    status_parser.add_argument("date", nargs="?", help="Date in YYYYMMDD format")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test run a cron job")
    test_parser.add_argument("job_name", help="Name of the job to test")

    # Cleanup command
    subparsers.add_parser("cleanup", help="Clean up old log files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_cron_jobs()
    elif args.command == "status":
        show_job_status(args.job_name, args.date)
    elif args.command == "test":
        success = test_job(args.job_name)
        sys.exit(0 if success else 1)
    elif args.command == "cleanup":
        cleanup_logs()


if __name__ == "__main__":
    main()
