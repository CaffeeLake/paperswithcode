"""Refresh paper 98109 evaluations from Cognition's FrontierCode leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.frontiercode_sync_service import (
    FrontierCodeSyncService,
    fetch_frontiercode_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncFrontierCodeJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_frontiercode", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_frontiercode_leaderboard()
        session = db_manager.session_local()
        try:
            stats = FrontierCodeSyncService(session).sync(
                leaderboard, commit=not self.dry_run
            )
            self.logger.info("frontiercode_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.selected)
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncFrontierCodeJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
