"""
Weekly task keyword backfill cron.

Re-scans all latest-version papers and inserts any missing ``paper_tasks``
rows with ``source = 'auto'`` using the current task keyword lists. This
backfills papers imported before a keyword was added or fixed; the daily HF
import cron only tags newly imported papers at insert time.

Schedule: weekly (see ``cron-link-papers-by-task-keywords.yml``).
Mode: add-only (never deletes existing auto or manual tags).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from scripts.utils.cron_helpers import CronJobBase

from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)


class TaskKeywordLinkWeeklyJob(CronJobBase):
    def __init__(self, rebuild: bool = False):
        super().__init__("link_papers_by_task_keywords_weekly")
        self.rebuild = rebuild

    def run(self) -> None:
        mode = "rebuild" if self.rebuild else "add-only"
        self.logger.info("Running task keyword linker in %s mode", mode)
        exit_code = link_papers_by_task_keywords(rebuild=self.rebuild)
        if exit_code != 0:
            raise RuntimeError(
                f"link_papers_by_task_keywords failed with exit code {exit_code}"
            )
        self.logger.info("Task keyword linker finished successfully")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Delete all source='auto' paper_tasks rows before re-inserting. "
            "Manual rows are preserved. Intended for manual runs only."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    job = TaskKeywordLinkWeeklyJob(rebuild=args.rebuild)
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
